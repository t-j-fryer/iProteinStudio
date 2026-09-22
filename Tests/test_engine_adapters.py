"""Shared registry preserves validated CLI arguments and rejects unknown engines."""
import importlib.util,os,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];scripts=ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path.insert(0,str(scripts))
from engine_adapters import command_for
from engine_registry import predictors,descriptor
class Tests(unittest.TestCase):
 def test_all_registered_prediction_commands(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);adapters=root/'adapters';input=root/'query.yaml';output=root/'out'
   for engine in predictors():
    cmd,env=command_for(engine,input,output,root,'v2',adapters)
    self.assertIn(str(input),cmd);self.assertIn(str(output),cmd)
    self.assertTrue(cmd[0].startswith(str(root/'venvs')))
    self.assertIn(descriptor(engine)['command_family'],{'boltz','intellifold','protenix','openfold3'})
    if engine=='boltz':self.assertEqual(cmd[1],str(root/'scripts/boltz_mps.py'))
    if engine=='intellifold':
     self.assertEqual(cmd[cmd.index('--model')+1],'v2');self.assertEqual(env['PYTORCH_ENABLE_MPS_FALLBACK'],'0')
    if engine.startswith('protenix-'):self.assertEqual(cmd[cmd.index('--model')+1],'mini' if engine.endswith('mini') else 'v2')
   with self.assertRaises(ValueError):command_for('unknown',input,output,root,'v2',adapters)
if __name__=='__main__':unittest.main()
