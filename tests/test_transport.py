import json
import socket
import threading
import unittest
from phonebridge import proto
from phonebridge.transport import Transport, BridgeError, CommandError, read_frame

class ProtocolTests(unittest.TestCase):
    def test_fragmented_frame(self):
        left, right = socket.socketpair()
        payload = proto.frame(0x1003, 4, 123, 999, 16, b'{"values":[1,2,3]}')
        def sender():
            for i in range(0, len(payload), 3): right.sendall(payload[i:i+3])
            right.close()
        threading.Thread(target=sender).start()
        try:
            frame = read_frame(left)
            self.assertEqual(frame[:5], (0x1003, 4, 123, 999, 16))
            self.assertEqual(json.loads(frame[5]), {'values': [1, 2, 3]})
        finally: left.close()

    def test_reject_oversized_payload(self):
        left, right = socket.socketpair()
        try:
            right.sendall(proto.HEADER.pack(b'PB01', 1, 1, 1, 1, 0, 0, 0xffffffff))
            with self.assertRaises(BridgeError): read_frame(left)
        finally: left.close(); right.close()

    def test_parallel_commands_and_negative_reply(self):
        left, right = socket.socketpair()
        transport = Transport('', '', lambda f: None, lambda m: None)
        transport.socks[1] = left
        def server():
            for _ in range(13):
                frame = read_frame(right)
                obj = json.loads(frame[5])
                result = {'ok': True, 'id': obj['id']}
                if obj['id'] == -1: result = {'ok': False, 'error': 'UNSUPPORTED'}
                right.sendall(proto.frame(0x13, 1, 1, 0, 0, json.dumps(result).encode()))
        worker = threading.Thread(target=server); worker.start()
        results = {}
        def client(i): results[i] = transport.request(0x12, {'id': i}, 0x13)['id']
        threads = [threading.Thread(target=client, args=(i,)) for i in range(12)]
        for t in threads: t.start()
        for t in threads: t.join(2)
        self.assertEqual(results, {i: i for i in range(12)})
        with self.assertRaises(CommandError): transport.request(0x12, {'id': -1}, 0x13)
        self.assertFalse(transport.closed.is_set())
        worker.join(2); transport.close(); right.close()

if __name__ == '__main__': unittest.main()
