"""Bounded public data inspection only; no model training."""
import hashlib, json, pathlib, time, urllib.request
import numpy as np
import scipy.io
import h5py
ROOT=pathlib.Path('/home/ec2-user/cadence-060-occlusion-data-20261001')
MAIN='94514806fb90da6f91193e86d97de7653c4a0247'
MODEL='3d772a6f797d20893e1639bfea2b9abe6b062573'
FILES={
 'occlusion-classification':[
  'data/features/klab325_orig/caffenet-fc7.mat',
  'data/features/data_occlusion_klab325v2/caffenet-fc7.mat',
  'data/data_occlusion_klab325v2.mat','data/data_occlusion_klab325v2_origimages.mat',
  'data/data_occlusion_klab325v3.mat','data/dataset_extended.mat',
  'data/data_occlusion_klab325v2-pres.txt','data/data_occlusion_klab325v2-categories.txt',
  'data/KLAB325.mat','data/README.md','run.m','runMaskedHopFeatures.m',
  'data/createOccludedImage.m','data/AddBubbles.m','data/createBubbles.m',
  'visualize/performance/collectAccuracies.m','visualize/partitionTrials.m',
  'visualize/correlation/collectModelHumanCorrelationData.m','.gitmodules'],
 'occlusion-models':[
  'runTask.m','evaluate.m','classifiers/LibsvmClassifierCCV.m','classifiers/LibsvmClassifier.m',
  'feature_extractors/hopfield/HopFeatures.m','computeHopTimeFeatures.m',
  'feature_extractors/provide/FeatureProvider.m','feature_extractors/bipolar/bipolarize.m']}
ROOT.mkdir(exist_ok=True)
report={'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'purpose':'read-only original-data inspection; no model training','source_commits':{'occlusion-classification':MAIN,'occlusion-models':MODEL},'license':'No top-level repository or explicit dataset license found in inspected source trees. Private experimental cache only, no asset redistribution.','files':[],'schema':{},'checks':{},'limitations':[]}
def write():
 (ROOT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
write()
for repo, paths in FILES.items():
 for path in paths:
  url=f'https://raw.githubusercontent.com/kreimanlab/{repo}/{MAIN if repo=="occlusion-classification" else MODEL}/{path}'
  dest=ROOT/repo/path;dest.parent.mkdir(parents=True,exist_ok=True)
  start=time.monotonic();digest=hashlib.sha256();size=0
  with urllib.request.urlopen(url,timeout=45) as source, dest.open('wb') as out:
   while chunk:=source.read(1024*1024):out.write(chunk);digest.update(chunk);size+=len(chunk)
  report['files'].append({'path':str(dest.relative_to(ROOT)),'url':url,'bytes':size,'sha256':digest.hexdigest(),'seconds':time.monotonic()-start})
  write();print(json.dumps(report['files'][-1]),flush=True)
base=ROOT/'occlusion-classification/data'
for label,path in [('whole_fc7',base/'features/klab325_orig/caffenet-fc7.mat'),('partial_fc7',base/'features/data_occlusion_klab325v2/caffenet-fc7.mat')]:
 with h5py.File(path,'r') as f:
  d=f['features']; lo=float('inf'); hi=-float('inf'); finite=True; zeros=0; count=0
  for start in range(0,d.shape[1],128):
   part=d[:,start:start+128];finite &= bool(np.isfinite(part).all());lo=min(lo,float(part.min()));hi=max(hi,float(part.max()));zeros+=int((part==0).sum());count+=part.size
  report['schema'][label]={'hdf5_shape':list(d.shape),'matlab_shape':list(reversed(d.shape)),'dtype':str(d.dtype),'uncompressed_bytes':d.size*d.dtype.itemsize,'finite':finite,'minimum':lo,'maximum':hi,'zero_fraction':zeros/count,'dataset_attributes':{k:str(v) for k,v in d.attrs.items()}}
  assert finite
pres=np.loadtxt(base/'data_occlusion_klab325v2-pres.txt',dtype=int);labels=np.loadtxt(base/'data_occlusion_klab325v2-categories.txt',dtype=int)
orig=scipy.io.loadmat(base/'data_occlusion_klab325v2_origimages.mat',squeeze_me=True,struct_as_record=False)['data'].truth
assert pres.shape==labels.shape==(13000,)
assert np.array_equal(np.unique(pres),np.arange(1,326))
assert np.array_equal(labels,orig[pres-1])
report['schema']['row_mapping']={'rows':len(pres),'object_ids':np.unique(pres).tolist(),'whole_labels':orig.tolist(),'category_ids':np.unique(labels).tolist(),'rows_per_object':dict(zip(*[x.tolist() for x in np.unique(pres,return_counts=True)])),'rows_per_class':dict(zip(*[x.tolist() for x in np.unique(labels,return_counts=True)])),'pres_first16':pres[:16].tolist(),'category_first16':labels[:16].tolist()}
report['checks']['pres_and_labels_match_whole_object_truth']=True
for name in ['data_occlusion_klab325v2.mat','data_occlusion_klab325v3.mat','dataset_extended.mat','KLAB325.mat']:
 try:
  d=scipy.io.loadmat(base/name,squeeze_me=True,struct_as_record=False)
  info={}
  for k,v in d.items():
   if k.startswith('__'):continue
   row={'type':type(v).__name__,'shape':list(getattr(v,'shape',[])),'dtype':str(getattr(v,'dtype',None))}
   if hasattr(v,'_fieldnames'):
    row['fields']={key:{'shape':list(getattr(getattr(v,key),'shape',[])),'type':type(getattr(v,key)).__name__} for key in v._fieldnames}
    for key in ['pres','truth','percentblack','percent_black','visibility','subject','soas','soa','masked','mask','response','correct']:
     if key in v._fieldnames:
      val=np.asarray(getattr(v,key));row.setdefault('simple_fields',{})[key]={'shape':list(val.shape),'unique_head':np.unique(val).tolist()[:100]}
   info[str(k)]=row
  report['schema'][name]=info
 except Exception as exc:report['schema'][name]={'error':repr(exc)}
report['limitations'] += ['MATLAB legacy dataset/MCOS behavioral objects require source-faithful decoding before visibility/SOA/mask/human analysis.', 'Original outer fold IDs not yet recovered: source uses MATLAB rng(1,twister), crossval object IDs; do not substitute NumPy split and call bit-identical reproduction.', 'Repository precomputed Hopfield path trains on all325 whole patterns before classifier CV; distinguish prior whole-pattern exposure from held-out classifier labels.', 'Original MATLAB newhop uses modified Hopfield construction: ordinary outer-product Hebb code alone is not proven equivalent.']
report['bytes_total']=sum(x['bytes'] for x in report['files'])
report['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
report['status']='numeric_features_and_object_label_alignment_verified; behavioral_decode_and_exact_folds_pending'
write();print(json.dumps({'status':report['status'],'bytes_total':report['bytes_total'],'schema':report['schema']},indent=2),flush=True)
