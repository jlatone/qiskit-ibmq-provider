# -*- coding: utf-8 -*-

# This code is part of Qiskit.
#
# (C) Copyright IBM 2017, 2018.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.


"""Tests for all IBMQ backends."""

from datetime import datetime
from unittest.mock import patch
from requests.exceptions import Timeout

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.providers.exceptions import QiskitBackendNotFoundError
from qiskit.providers.ibmq.accountprovider import AccountProvider
from qiskit.providers.ibmq.ibmqfactory import IBMQFactory
from qiskit.providers.ibmq.ibmqbackend import IBMQSimulator
from qiskit.qobj import QobjHeader
from qiskit.test import slow_test, providers
from qiskit.compiler import assemble, transpile
from qiskit.providers.models.backendproperties import BackendProperties
from qiskit.providers.ibmq.api_v2.session import Session

from ..decorators import (requires_qe_access,
                          requires_new_api_auth)
from ..ibmqtestcase import IBMQTestCase


class TestAccountProvider(IBMQTestCase, providers.ProviderTestCase):
    """Tests for all the IBMQ backends through the new API."""

    provider_cls = AccountProvider
    backend_name = 'ibmq_qasm_simulator'

    def setUp(self):
        """Required method for testing"""
        super().setUp()
        qr = QuantumRegister(1)
        cr = ClassicalRegister(1)
        self.qc1 = QuantumCircuit(qr, cr, name='circuit0')
        self.qc1.h(qr[0])
        self.qc1.measure(qr, cr)

    @requires_qe_access
    @requires_new_api_auth
    def _get_provider(self, qe_token, qe_url):
        """Return an instance of a Provider."""
        # pylint: disable=arguments-differ
        ibmq = IBMQFactory()
        return ibmq.enable_account(qe_token, qe_url)

    def test_remote_backends_exist_real_device(self):
        """Test if there are remote backends that are devices."""
        remotes = self.provider.backends(simulator=False)
        self.assertTrue(remotes)

    def test_remote_backends_exist_simulator(self):
        """Test if there are remote backends that are simulators."""
        remotes = self.provider.backends(simulator=True)
        self.assertTrue(remotes)

    def test_remote_backends_instantiate_simulators(self):
        """Test if remote backends that are simulators are an IBMQSimulator instance."""
        remotes = self.provider.backends(simulator=True)
        for backend in remotes:
            with self.subTest(backend=backend):
                self.assertIsInstance(backend, IBMQSimulator)

    def test_remote_backend_status(self):
        """Test backend_status."""
        for backend in self.provider.backends():
            _ = backend.status()

    def test_remote_backend_configuration(self):
        """Test backend configuration."""
        remotes = self.provider.backends()
        for backend in remotes:
            _ = backend.configuration()

    def test_remote_backend_properties(self):
        """Test backend properties."""
        remotes = self.provider.backends(simulator=False)
        for backend in remotes:
            properties = backend.properties()
            if backend.configuration().simulator:
                self.assertEqual(properties, None)

    def test_remote_backend_pulse_defaults(self):
        """Test backend pulse defaults."""
        remotes = self.provider.backends(simulator=False)
        for backend in remotes:
            defaults = backend.defaults()
            if backend.configuration().open_pulse:
                self.assertIsNotNone(defaults)
            else:
                self.assertIsNone(defaults)

    def test_qobj_headers_in_result_sims(self):
        """Test that the qobj headers are passed onto the results for sims."""
        backends = self.provider.backends(simulator=True)

        custom_qobj_header = {'x': 1, 'y': [1, 2, 3], 'z': {'a': 4}}

        for backend in backends:
            with self.subTest(backend=backend):
                circuits = transpile(self.qc1, backend=backend)

                qobj = assemble(circuits, backend=backend)
                # Update the Qobj header.
                qobj.header = QobjHeader.from_dict(custom_qobj_header)
                qobj.experiments[0].header.some_field = 'extra info'

                result = backend.run(qobj).result()
                self.assertEqual(result.header.to_dict(), custom_qobj_header)
                self.assertEqual(result.results[0].header.some_field,
                                 'extra info')

    @slow_test
    def test_qobj_headers_in_result_devices(self):
        """Test that the qobj headers are passed onto the results for devices."""
        backends = self.provider.backends(simulator=False)

        custom_qobj_header = {'x': 1, 'y': [1, 2, 3], 'z': {'a': 4}}

        for backend in backends:
            with self.subTest(backend=backend):
                circuits = transpile(self.qc1, backend=backend)

                qobj = assemble(circuits, backend=backend)
                # Update the Qobj header.
                qobj.header = QobjHeader.from_dict(custom_qobj_header)
                # Update the Qobj.experiment header.
                qobj.experiments[0].header.some_field = 'extra info'

                result = backend.run(qobj).result()
                self.assertEqual(result.header.to_dict(), custom_qobj_header)
                self.assertEqual(result.results[0].header.some_field,
                                 'extra info')

    def test_aliases(self):
        """Test that display names of devices map the regular names."""
        aliased_names = self.provider._aliased_backend_names()

        for display_name, backend_name in aliased_names.items():
            with self.subTest(display_name=display_name,
                              backend_name=backend_name):
                try:
                    backend_by_name = self.provider.get_backend(backend_name)
                except QiskitBackendNotFoundError:
                    # The real name of the backend might not exist
                    pass
                else:
                    backend_by_display_name = self.provider.get_backend(
                        display_name)
                    self.assertEqual(backend_by_name, backend_by_display_name)
                    self.assertEqual(
                        backend_by_display_name.name(), backend_name)

    def test_remote_backend_properties_filter_date(self):
        """Test backend properties filtered by date."""
        backends = self.provider.backends(simulator=False)

        datetime_filter = datetime(2019, 2, 1).replace(tzinfo=None)
        for backend in backends:
            with self.subTest(backend=backend):
                properties = backend.properties(datetime=datetime_filter)
                if isinstance(properties, BackendProperties):
                    last_update_date = properties.last_update_date.replace(tzinfo=None)
                    self.assertLessEqual(last_update_date, datetime_filter)
                else:
                    self.assertEqual(properties, None)

    def test_provider_backends(self):
        """Test provider_backends have correct attributes."""
        provider_backends = {back for back in dir(self.provider.provider_backends)
                             if not back.startswith('_')}
        backends = {back.name() for back in self.provider.backends()}
        self.assertEqual(provider_backends, backends)

    def test_provider_backends_timeout(self):
        """Test provider_backends timeout."""
        with patch.object(Session, "request", side_effect=Timeout):
            provider_backends = {
                back for back in dir(self.provider.provider_backends)
                if not back.startswith('_')}
        self.assertEqual(len(provider_backends), 0)
