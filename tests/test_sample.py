import unittest
from youtube_dl_playlist import Downloader


class TestDownloader(unittest.TestCase):

    def test_name(self):
        s = Downloader()
        self.assertEqual(s.name(), "my name")


if __name__ == '__main__':
    unittest.main()
