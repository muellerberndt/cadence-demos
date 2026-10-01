"""Validate original public Tang data without modifying arrays or training."""
import hashlib,io,json,pathlib,time
import h5py,numpy as np,scipy.io
from scipy.io.matlab._mio5 import MatFile5Reader
R=pathlib.Path('/home/ec2-user/cadence-060-occlusion-data-20261001')
p=R/'occlusion-classification/data';m=json.loads((R/'manifest.json').read_text())
def sha(f):
 h=hashlib.sha256()
 with f.open('rb') as s:
  while c:=s.read(1048576):h.update(c)
 return h.hexdigest()
for f in m['files']:assert sha(R/f['path'])==f['sha256']
m['checks']['all_downloaded_source_hashes_unchanged']=True
for label,f in [('whole_fc7',p/'features/klab325_orig/caffenet-fc7.mat'),('partial_fc7',p/'features/data_occlusion_klab325v2/caffenet-fc7.mat')]:
 if h5py.is_hdf5(f):
  with h5py.File(f) as hf:a=np.array(hf['features']).T
  fmt='MATLAB7.3/HDF5 transposed to MATLAB row order'
 else:a=scipy.io.loadmat(f)['features'];fmt='MATLAB5 compressed array; already row-major semantic shape'
 assert a.shape==((325,4096) if label=='whole_fc7' else (13000,4096))
 assert np.isfinite(a).all()
 m['schema'][label]={'container':fmt,'shape':list(a.shape),'dtype':str(a.dtype),'uncompressed_bytes':a.nbytes,'finite':True,'minimum':float(a.min()),'maximum':float(a.max()),'zero_fraction':float((a==0).mean())}
 del a
pres=np.loadtxt(p/'data_occlusion_klab325v2-pres.txt',dtype=int);labels=np.loadtxt(p/'data_occlusion_klab325v2-categories.txt',dtype=int)
orig=scipy.io.loadmat(p/'data_occlusion_klab325v2_origimages.mat',squeeze_me=True,struct_as_record=False)['data'].truth
assert pres.shape==labels.shape==(13000,)
assert np.array_equal(np.unique(pres),np.arange(1,326))
assert np.array_equal(labels,orig[pres-1])
m['schema']['row_mapping']={'rows':len(pres),'object_ids':np.unique(pres).tolist(),'whole_labels':orig.tolist(),'category_ids':np.unique(labels).tolist(),'rows_per_object':dict(zip(*[x.tolist() for x in np.unique(pres,return_counts=True)])),'rows_per_class':dict(zip(*[x.tolist() for x in np.unique(labels,return_counts=True)])),'pres_first16':pres[:16].tolist(),'category_first16':labels[:16].tolist()}
m['checks']['pres_and_labels_match_whole_object_truth']=True
# Parse this pinned legacy MATLAB MCOS dataset, then independently verify its mappings.
d=scipy.io.loadmat(p/'data_occlusion_klab325v2.mat')
w=d['__function_workspace__'].tobytes();s=io.BytesIO(w)
r=MatFile5Reader(s,squeeze_me=True,struct_as_record=False,byte_order='<');r.initialize_read();s.seek(8)
h,_=r.read_var_header();arr=r.read_var_array(h).MCOS['arr'][0]
assert len(arr)==7 and arr[2]==13000 and arr[3]==17
cols=dict(zip(arr[4],arr[5]));assert len(cols)==17
assert np.array_equal(cols['pres'],pres);assert np.array_equal(cols['truth'],labels)
assert np.array_equal(cols['correct'],cols['response_category']==cols['truth'])
m['checks']['mcos_object_labels_and_correctness_crosschecked']=True
m['schema']['behavior']={'rows':13000,'columns':{k:{'shape':list(v.shape),'dtype':str(v.dtype),'minimum':float(v.min()),'maximum':float(v.max())} for k,v in cols.items()},'soa_seconds':np.unique(cols['soa']).tolist(),'subject_ids':np.unique(cols['subject']).tolist(),'masked_counts':dict(zip(*[x.tolist() for x in np.unique(cols['masked'],return_counts=True)])),'black_percentiles':np.quantile(cols['black'],[0,.25,.5,.75,1]).tolist(),'visible_percentiles':np.quantile(100-cols['black'],[0,.25,.5,.75,1]).tolist()}
images=scipy.io.loadmat(p/'KLAB325.mat',squeeze_me=True,struct_as_record=False)
m['schema']['whole_images']={k:{'shape':list(v.shape),'dtype':str(v.dtype),'first_shape':list(v.flat[0].shape) if v.dtype==object else None} for k,v in images.items() if not k.startswith('__')}
assert images['img_mat'].size==325
m['limitations']=['Exact outer-fold object IDs not yet recovered: MATLAB rng(1,twister) and crossval. NumPy folds are not a bit-identical substitute.','The source precomputed Hopfield route learns all325 whole patterns before classifier CV; this is prior pattern exposure, even when classifier labels are held out.','MATLAB newhop is a modified Hopfield construction; no equivalence claim for plain Hebbian outer-product implementations.','This legacy-MCOS parser is scoped to the exact pinned dataset and independently crosschecked for IDs, labels, correctness; no claim of general MCOS support.','No model training, baseline reproduction, mask feature generation or Cadence capability test has run.']
m['bytes_total']=sum(x['bytes'] for x in m['files']);m['preparation_attempts']=[{'attempt':1,'status':'missing scipy; no downloads'},{'attempt':2,'status':'all downloads complete; mixed MAT container assumption failed'},{'attempt':3,'status':'numeric and metadata verification completed with separate MAT5/HDF5 readers'}]
m['dependency_isolation']='scipy and h5py installed under this directory/deps with --no-deps; frozen venv unchanged'
m['status']='verified_original_feature_shapes_finite_values_and_row_alignment_with_behavior_and_labels'
m['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
(R/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps({'status':m['status'],'bytes_total':m['bytes_total'],'features':{k:v for k,v in m['schema'].items() if k.endswith('_fc7')},'behavior_summary':{k:v for k,v in m['schema']['behavior'].items() if k!='columns'},'manifest_sha256':sha(R/'manifest.json')},indent=2))
