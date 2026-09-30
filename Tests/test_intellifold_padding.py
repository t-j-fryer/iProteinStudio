import importlib.util,unittest
from pathlib import Path
path=Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/scripts/intellifold_padding.py'
spec=importlib.util.spec_from_file_location('intellifold_padding',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class PaddingPolicy(unittest.TestCase):
    def test_both_models_use_native_exact_size_path(self):
        for model in ('v2','v2-flash'):
            self.assertEqual(m.default_buckets(model),'1')
            self.assertEqual(m.launcher_arguments(['input','--model='+model])[-2:],['--buckets','1'])
    def test_user_override_is_preserved(self):
        for args in [['input','--buckets','256,512'],['input','--buckets=64,128']]:
            self.assertEqual(m.launcher_arguments(args),args)
    def test_default_flash_and_explicit_model(self):
        for args in [['input'],['input','--model','v2-flash']]:
            self.assertEqual(m.launcher_arguments(args)[-2:],['--buckets',m.default_buckets('v2-flash')])
if __name__=='__main__':unittest.main()
