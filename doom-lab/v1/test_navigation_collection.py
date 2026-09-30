import unittest
from .navigation_collection import selected_indices


class SelectionTests(unittest.TestCase):
    def test_no_fabrication_or_duplicate_short_episode(self):
        for length in range(40):
            indices=selected_indices(length)
            self.assertEqual(len(indices),min(16,length))
            self.assertEqual(indices,sorted(set(indices)))
            self.assertTrue(all(0<=i<length for i in indices))
            if length:self.assertEqual(indices[-1],length-1)
            if length<16:self.assertEqual(indices,list(range(length)))

    def test_prospective_even_spacing_and_invalid(self):
        self.assertEqual(selected_indices(526),list(range(0,526,35)))
        for bad in [-1,1.2,True]:
            with self.assertRaises(ValueError):selected_indices(bad)


if __name__=='__main__':unittest.main()
