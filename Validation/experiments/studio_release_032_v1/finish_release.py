"""Publish an authorized, unchanged draft after the declared Studio checks pass.

Uses the prior release gate's queue/readiness helpers. No scientific execution.
"""
import argparse,datetime,fcntl,hashlib,importlib.util,json,os,plistlib,shutil,subprocess,time
from pathlib import Path
previous=Path(__file__).resolve().parents[1]/'studio_release_031_v1/finish_release.py'
spec=importlib.util.spec_from_file_location('release031',previous);prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
run,sha=prior.run,prior.sha

def cohort(manifest):
 jobs=[]
 for path in manifest['ledgers']:jobs+=prior.prepared_jobs(Path(path))
 names=[j['name'] for j in jobs]
 if len(set(names))!=len(names):raise ValueError('Duplicate release acceptance route')
 if not set(names)<=set(manifest['expected_names']):raise ValueError('Unexpected acceptance route')
 return jobs

def validated(app,version,build,beta=False):
 app=Path(app);run(['/usr/bin/codesign','--verify','--deep','--strict',app])
 info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
 assert info['CFBundleShortVersionString']==version and str(info['CFBundleVersion'])==str(build)
 assert info['CFBundleIdentifier']==('ai.nanohunter.studio.local-beta' if beta else 'ai.nanohunter.studio')
 assert bool(info.get('IPStudioSparkleUpdateBuild')) is (not beta)

def main():
 p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);a=p.parse_args();m=json.loads(a.manifest.read_text());out=a.manifest.resolve().parent
 lock=(out/'delivery.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 def status(phase,**extra):
  data=dict(phase=phase,updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=os.getpid(),**extra)
  temp=out/'delivery-status.part';temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(out/'delivery-status.json')
 try:
  if (out/'delivery-completed.json').exists():return
  public=Path(m['public']);agent=Path(m['agent']);repo=m['github_repo'];tag=m['tag']
  status('waiting_for_gpu_qualification')
  while True:
   jobs=cohort(m)
   if prior.ready(jobs,agent,count=len(m['expected_names'])):break
   if len(jobs)<len(m['expected_names']):
    process=m['preparation_process']
    try:born=run(['/bin/ps','-p',str(process['pid']),'-o','lstart='])
    except subprocess.CalledProcessError:born=''
    if born!=process['born']:raise RuntimeError('Preparation ended before all acceptance routes were queued; publication held.')
   time.sleep(30)
  status('auditing_completed_outputs')
  for path,digest in m['files'].items():assert sha(path)==digest,'Retained artifact changed: '+path
  run([m['python'],m['audit_script'],out]);audit=json.loads((out/'audit.json').read_text());assert audit['passed']
  assert run(['git','rev-parse','HEAD'],public)==m['public_commit'],'Candidate changed'
  assert not run(['git','status','--porcelain'],public),'Candidate is dirty'
  assert run(['git','ls-remote','https://github.com/'+repo+'.git','refs/heads/main']).split()[0]==m['public_main'],'Public main changed'
  release=json.loads(run(['gh','release','view',tag,'--repo',repo,'--json','isDraft,assets']));assert release['isDraft'],'Release is no longer a draft'
  validated(m['public_app'],m['version'],m['build']);validated(m['beta_app'],m['version']+'-dev',m['build'],True)
  q=out/'RELEASE_QUALIFICATION.json';q.write_text(json.dumps(dict(audit,source_commit=m['public_commit'],offline_checks=m['offline_checks']),indent=2)+'\n')
  status('publishing_verified_release')
  run(['gh','release','upload',tag,'--repo',repo,q,'--clobber'])
  if not run(['git','tag','--list',tag],public):run(['git','tag','-a',tag,'-m','iProteinStudio '+m['version']+' trusted beta',m['public_commit']],public)
  assert run(['git','rev-list','-n','1',tag],public)==m['public_commit']
  run(['git','push','https://github.com/'+repo+'.git','refs/tags/'+tag],public)
  notes=Path(m['notes']).read_text().replace('QUALIFICATION_PENDING','All six declared acceptance routes passed the retained-output audit. These are bounded software integration checks, not experimental binding or performance claims.')
  published_notes=out/'published-notes.md';published_notes.write_text(notes)
  run(['gh','release','edit',tag,'--repo',repo,'--draft=false','--prerelease','--notes-file',published_notes])
  published=json.loads(run(['gh','api','repos/'+repo+'/releases/tags/'+tag]));assert not published['draft']
  assets={a['name']:a for a in published['assets']}
  for path in m['assets']:
   f=Path(path);asset=assets[f.name];assert asset['size']==f.stat().st_size and asset.get('digest')=='sha256:'+sha(f),'Uploaded asset changed'
  shutil.copy2(m['appcast'],public/'appcast.xml')
  lab=public/'lab_book/0727-publish-unified-design-release.md'
  lab.write_text(lab.read_text()+'\n## Public delivery\n\nAll six acceptance routes passed the immutable-output audit. Published '+tag+' from '+m['public_commit']+'; RELEASE_QUALIFICATION.json accompanies the assets. This is bounded technical acceptance, not efficacy.\n')
  run(['git','add','--','appcast.xml','lab_book/0727-publish-unified-design-release.md'],public)
  run(['git','commit','-m','Publish verified Studio '+m['version']+' update feed'],public)
  run(['git','push','https://github.com/'+repo+'.git','HEAD:main','HEAD:refs/heads/release/paper-next'],public)
  status('published_waiting_for_idle_apps_and_queue',release_url=published['html_url'])
  while True:
   active=[p for p in (agent/'jobs').glob('*/state.json') if json.loads(p.read_text()).get('status') in ('running','queued','stopping')]
   processes=run(['/bin/ps','-axo','command=']).splitlines()
   apps_open=any(line.startswith('/Applications/iProteinStudio.app/Contents/MacOS/') or line.startswith('/Applications/iProteinStudio Beta.app/Contents/MacOS/') for line in processes)
   if not active and not apps_open:break
   time.sleep(30)
  status('installing_verified_apps');backups=out/'installed-backups';backups.mkdir(exist_ok=True)
  for source,name,version,beta in [(Path(m['public_app']),'iProteinStudio.app',m['version'],False),(Path(m['beta_app']),'iProteinStudio Beta.app',m['version']+'-dev',True)]:
   dest=Path('/Applications')/name;stage=Path('/Applications')/('.studio032-'+name)
   identity=['Contents/Info.plist','Contents/_CodeSignature/CodeResources','Contents/MacOS/iProteinStudio']
   current={rel:sha(dest/rel) for rel in identity} if dest.exists() else None
   if current=={rel:sha(source/rel) for rel in identity}:continue
   assert current==m['installed'][name],'Installed application changed since preparation'
   assert not stage.exists();run(['/usr/bin/ditto',source,stage]);validated(stage,version,m['build'],beta)
   backup=backups/name;assert not backup.exists()
   if dest.exists():dest.rename(backup)
   try:stage.rename(dest)
   except Exception:
    if backup.exists():backup.rename(dest)
    raise
   validated(dest,version,m['build'],beta)
  env=dict(os.environ,IPROTEINSTUDIO_RESOURCE_ROOT='/Applications/iProteinStudio.app/Contents/Resources/iProteinStudioResources');env.pop('IPROTEINSTUDIO_TEST_SUPPORT_ROOT',None)
  run([m['stage_helper']],env=env)
  doctor=json.loads(run([m['python'],agent.parent/'mcp/studioctl.py','doctor']))
  assert doctor['ok'] and doctor['bridge_version']==str(m['bridge'])
  done=dict(version=m['version'],build=m['build'],bridge=m['bridge'],release_url=published['html_url'],backups=str(backups))
  (out/'delivery-completed.json').write_text(json.dumps(done,indent=2)+'\n');status('complete',**done)
 except Exception as exc:status('stopped',error=str(exc));raise
if __name__=='__main__':main()
