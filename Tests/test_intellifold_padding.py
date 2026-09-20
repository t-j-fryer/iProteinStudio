import importlib.util,unittest
from pathlib import Path
path=Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/scripts/intellifold_padding.py'
spec=importlib.util.spec_from_file_location('intellifold_padding',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class PaddingPolicy(unittest.TestCase):
    def test_only_small_flash_bucket_changes(self):
        original=[int(x) for x in m.UPSTREAM_BUCKETS.split(',')]
        candidate=[int(x) for x in m.default_buckets('v2-flash').split(',')]
        self.assertEqual(candidate,[128]+original)
        for size in range(129,5121):
            self.assertEqual(next(x for x in original if x>=size),next(x for x in candidate if x>=size))
    def test_full_preserves_default(self):
        self.assertEqual(m.default_buckets('v2'),m.UPSTREAM_BUCKETS)
        self.assertEqual(m.launcher_arguments(['input','--model=v2'])[-1],m.UPSTREAM_BUCKETS)
    def test_user_override_is_preserved(self):
        for args in [['input','--buckets','256,512'],['input','--buckets=64,128']]:
            self.assertEqual(m.launcher_arguments(args),args)
    def test_default_flash_and_explicit_model(self):
        for args in [['input'],['input','--model','v2-flash']]:
            self.assertEqual(m.launcher_arguments(args)[-2:],['--buckets',m.default_buckets('v2-flash')])
if __name__=='__main__':unittest.main()
