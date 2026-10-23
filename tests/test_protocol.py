import socket
import unittest

from szasar import (
    LineTooLong,
    SocketReader,
    decode_path,
    encode_path,
    recvline,
)


class SocketReaderTests(unittest.TestCase):
    def make_reader(self, max_line=8192):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        return SocketReader(left, max_line=max_line), right

    def test_reads_crlf_across_chunks(self):
        reader, writer = self.make_reader()
        writer.sendall(b"first\r")
        writer.sendall(b"\nsecond\r\n")

        self.assertEqual(reader.readline(), b"first")
        self.assertEqual(reader.readline(), b"second")

    def test_empty_line(self):
        reader, writer = self.make_reader()
        writer.sendall(b"\r\n")

        self.assertEqual(reader.readline(), b"")

    def test_line_too_long(self):
        reader, writer = self.make_reader(max_line=4)
        writer.sendall(b"12345\r\n")

        with self.assertRaises(LineTooLong):
            reader.readline()

    def test_read_exact_after_line(self):
        reader, writer = self.make_reader()
        writer.sendall(b"line\r\npayload")

        self.assertEqual(reader.readline(), b"line")
        self.assertEqual(reader.read_exact(7), b"payload")

    def test_readline_keeps_eol_when_requested(self):
        reader, writer = self.make_reader()
        writer.sendall(b"line\r\n")

        self.assertEqual(reader.readline(remove_eol=False), b"line\r\n")

    def test_recvline_has_a_length_limit(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        right.sendall(b"12345\r\n")

        with self.assertRaises(LineTooLong):
            recvline(left, max_length=4)


class PathEncodingTests(unittest.TestCase):
    def test_encodes_spaces_tabs_and_question_marks(self):
        encoded = encode_path("dir/a b\tc?d.txt")

        self.assertNotIn(" ", encoded)
        self.assertNotIn("\t", encoded)
        self.assertNotIn("?", encoded)

    def test_round_trip(self):
        path = "shared/@owner/dir/a b\tc?d.txt"

        self.assertEqual(decode_path(encode_path(path)), path)

    def test_encodes_leading_at_sign(self):
        self.assertEqual(encode_path("@owner/file"), "%40owner/file")

    def test_keeps_path_separators(self):
        self.assertEqual(encode_path("dir/sub/file.txt"), "dir/sub/file.txt")


if __name__ == "__main__":
    unittest.main()
