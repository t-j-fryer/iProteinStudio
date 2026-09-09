import unittest
import campaign as c

class Contracts(unittest.TestCase):
    def test_complete_declared_matrix(self):
        self.assertEqual(len(c.CONFIG['arms']), 21)
        variants={(a['predictor'],a['model']) for a in c.CONFIG['arms'].values()}
        self.assertEqual(len(variants),7)
        for variant in variants:
            self.assertEqual({a['strength'] for a in c.CONFIG['arms'].values() if (a['predictor'],a['model'])==variant},{0,.5,1})
    def test_paired_seeds_and_initialization_only(self):
        for arm in c.CONFIG['arms'].values():
            for phase,n,offset in [('pilot',1,0),('remaining',9,1)]:
                args=c.arguments_for(arm,phase)
                options=dict(zip(args[::2],args[1::2])) if False else None
                def value(flag):return args[args.index(flag)+1]
                self.assertEqual(value('--num-runs'),str(n))
                self.assertEqual(value('--num-opt-cycles'),'5')
                self.assertEqual(value('--binder-min-len'),'90')
                self.assertEqual(value('--binder-max-len'),'90')
                self.assertEqual(value('--binder-random-seed'),str(906000+offset))
                self.assertEqual(value('--mpnn-seed'),str(1906000+1000*offset))
                self.assertEqual(value('--negative-helix-constant'),str(arm['strength']))
                self.assertNotIn('--secondary-bias-scope',args)
                self.assertNotIn('--initialization-max-attempts',args)

if __name__=='__main__':unittest.main()
