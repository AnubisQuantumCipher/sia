"""Deleting an already-yielded terminal row must not evade length guards."""
import unittest

import siaeventintake as intake
import siaeventplan as pages
import siasourcebatch as source


class TerminalPairDrift(unittest.TestCase):
    def test_terminal_deletion_is_refused_at_each_pairing_boundary(self):
        for module, reasons in ((intake, ()), (pages, ('fixture-roster',)),
                                (source, ('fixture-roster',))):
            for count in (1, 2):
                for side in ('left', 'right', 'both'):
                    with self.subTest(module=module.__name__, count=count, side=side):
                        left, right = list(range(count)), list(range(count))
                        pairs = module._paired_rows(left, right, *reasons)
                        for expected in range(count):
                            self.assertEqual(next(pairs), (expected, expected))
                        targets = (left, right) if side == 'both' else (
                            left if side == 'left' else right,)
                        for target in targets:
                            target.pop()
                        with self.assertRaises(ValueError) as caught:
                            next(pairs)
                        reason = 'complete-collector-roster' if module is intake else 'fixture-roster'
                        self.assertIn(reason, str(caught.exception))


if __name__ == '__main__':
    unittest.main()
