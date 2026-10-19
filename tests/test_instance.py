import unittest
from unittest.mock import Mock, patch
from phonebridge.instance import AppInstance


class InstanceTests(unittest.TestCase):
    def kernel(self):
        return Mock(CreateMutexW=Mock(return_value=101),CreateEventW=Mock(return_value=102),
                    WaitForSingleObject=Mock(return_value=258))

    def test_first_owner_holds_mutex_and_activation_event(self):
        kernel=self.kernel()
        with patch('ctypes.get_last_error',return_value=0):
            owner=AppInstance('C:/Example',kernel=kernel)
        self.assertTrue(owner.primary)
        kernel.SetEvent.assert_not_called()
        self.assertFalse(owner.take_activation())
        kernel.WaitForSingleObject.return_value=0
        self.assertTrue(owner.take_activation())
        owner.close();owner.close()
        self.assertEqual(kernel.CloseHandle.call_count,2)

    def test_duplicate_only_signals_existing_instance(self):
        kernel=self.kernel()
        with patch('ctypes.get_last_error',return_value=183):
            second=AppInstance('C:/Example',kernel=kernel)
        self.assertFalse(second.primary)
        kernel.SetEvent.assert_called_once_with(102)
        self.assertFalse(second.take_activation())
        second.close()

    def test_duplicate_headless_does_not_open_a_window(self):
        kernel=self.kernel()
        with patch('ctypes.get_last_error',return_value=183):
            second=AppInstance('C:/Example',activate=False,kernel=kernel)
        kernel.SetEvent.assert_not_called()
        second.close()

    def test_different_workspaces_have_different_names(self):
        kernel=self.kernel()
        with patch('ctypes.get_last_error',return_value=0):
            first=AppInstance('C:/Example1',kernel=kernel)
            second=AppInstance('C:/Example2',kernel=kernel)
        names=[call.args[2] for call in kernel.CreateMutexW.call_args_list]
        self.assertNotEqual(names[0],names[1])
        first.close();second.close()


if __name__=='__main__':
    unittest.main()
