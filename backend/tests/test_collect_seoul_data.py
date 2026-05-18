import io
import unittest

from backend.scripts.collect_seoul_data import read_license_csv


class CollectSeoulDataTest(unittest.TestCase):
    def test_read_license_csv_skips_malformed_rows(self):
        csv_text = "번호,사업장명\n1,정상업소\n2,깨진,행\n3,다음업소\n"

        result = read_license_csv(io.BytesIO(csv_text.encode("cp949")))

        self.assertEqual(list(result["사업장명"]), ["정상업소", "다음업소"])


if __name__ == "__main__":
    unittest.main()
