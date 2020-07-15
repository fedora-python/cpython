import sys
from test import test_support
import unittest

crypt = test_support.import_module('crypt')

if sys.platform.startswith('openbsd'):
    raise unittest.SkipTest('The only supported method on OpenBSD is Blowfish')

class CryptTestCase(unittest.TestCase):

    def test_crypt(self):
        cr = crypt.crypt('mypassword', 'ab')
        if cr is not None:
            cr2 = crypt.crypt('mypassword', cr)
            self.assertEqual(cr2, cr)


    def test_salt(self):
        self.assertEqual(len(crypt._saltchars), 64)
        for method in crypt.methods:
            salt = crypt.mksalt(method)
            self.assertEqual(len(salt),
                    method.salt_chars + (3 if method.ident else 0))

    def test_saltedcrypt(self):
        for method in crypt.methods:
            pw = crypt.crypt('assword', method)
            self.assertEqual(len(pw), method.total_size)
            pw = crypt.crypt('assword', crypt.mksalt(method))
            self.assertEqual(len(pw), method.total_size)

    def test_methods(self):
        # Gurantee that METHOD_CRYPT is the last method in crypt.methods.
        self.assertTrue(len(crypt.methods) >= 1)
        self.assertEqual(crypt.METHOD_CRYPT, crypt.methods[-1])

def test_main():
    test_support.run_unittest(CryptTestCase)

if __name__ == "__main__":
    test_main()
