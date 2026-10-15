"""Fixed read-only Linux diagnostic program; parameters arrive only as JSON stdin."""

PROGRAM = r"""
import json,os,signal,stat,shutil,time,sys
def timeout(*_): raise TimeoutError()
signal.signal(signal.SIGALRM,timeout);signal.alarm(7)
request=json.loads(sys.stdin.buffer.read(8193));result={'version':1,'connected':True}
if request['operation']=='inspect':
 result.update(cpu_threads=os.cpu_count(),architecture=os.uname().machine,
               ram=None,models=[],processes=[],directory_status='Unavailable',truncated=False,
               process_status='Unavailable',process_truncated=False)
 try:
  with open('/proc/meminfo') as f:
   for line in f:
    if line.startswith('MemTotal:'):result['ram']=int(line.split()[1])*1024;break
 except OSError:pass
 directory=request['models_dir']
 try:
  usage=shutil.disk_usage(directory);result['disk_free']=usage.free
  with os.scandir(directory) as entries:
   for i,item in enumerate(entries):
    if i>=500:result['truncated']=True;break
    if item.is_symlink():continue
    kind=None;size=None
    if item.is_file(follow_symlinks=False) and item.name.lower().endswith('.gguf'):
     kind='GGUF';size=item.stat(follow_symlinks=False).st_size
    elif item.is_dir(follow_symlinks=False) and os.path.isfile(item.path+'/config.json'):
     kind='Model directory'
    if kind:
     result['models'].append({'name':item.name[:240],'kind':kind,'size':size})
    if len(result['models'])>=100:result['truncated']=True;break
  result['directory_status']='Available';result['models'].sort(key=lambda x:x['name'])
 except (OSError,ValueError):pass
 result['tools']=[{'name':n,'path':shutil.which(n,path='/usr/local/bin:/usr/bin:/bin')}
                  for n in ('ollama','llama-server','vllm')]
 try:
  with os.scandir('/proc') as entries:
   result['process_status']='Available'
   for i,item in enumerate(entries):
    if i>=4096:result['process_truncated']=True;break
    if not item.name.isdecimal():continue
    try:
     with open(item.path+'/comm') as f:name=f.read(80).strip()
     if name in ('ollama','llama-server','vllm') or name.startswith('VLLM'):
      result['processes'].append({'pid':int(item.name),'name':name})
      if len(result['processes'])>=32:result['process_truncated']=True;break
    except OSError:pass
 except OSError:pass
signal.alarm(0)
print(json.dumps(result,separators=(',',':')))
"""
