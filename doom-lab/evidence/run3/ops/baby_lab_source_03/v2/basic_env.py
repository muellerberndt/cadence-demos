"""Pinned Basic six-action environment and the historical teacher's pixel transform."""
from __future__ import annotations

import hashlib
import importlib
import os
from pathlib import Path
import platform
import sys
import tempfile

import numpy as np

ACTIONS=((0,0,0),(1,0,0),(0,1,0),(0,0,1),(1,0,1),(0,1,1))
ACTION_NAMES=('noop','left','right','fire','left_fire','right_fire')
TRANSFORM='basic-gray320-area30x45-area15x15-zclip-v1'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def engine():
    target=os.environ.get('VIZDOOM_PYTHON_TARGET')
    if target and target not in sys.path: sys.path.insert(0,target)
    vzd=importlib.import_module('vizdoom')
    if vzd.__version__!='1.3.1': raise RuntimeError('This campaign requires ViZDoom 1.3.1')
    return vzd

def identity():
    vzd=engine();root=Path(vzd.root_path)
    return {'version':vzd.__version__,
            'files':{str(p.relative_to(root)):{'sha256':sha(p),'bytes':p.stat().st_size}
                     for p in sorted(root.rglob('*')) if p.is_file() and p.suffix!='.pyc'}}

def platform_identity():
    return {'system':platform.system(),'machine':platform.machine(),'python':sys.version,
            'numpy':np.__version__,'engine':identity()}

def area_matrix(source,target):
    left=np.arange(target,dtype=float)*source/target
    right=np.arange(1,target+1,dtype=float)*source/target
    return np.maximum(0,np.minimum(right[:,None],np.arange(1,source+1))-
                      np.maximum(left[:,None],np.arange(source)))/(source/target)

XAREA=area_matrix(320,45)
YAREA=area_matrix(240,30)

def pool(raw):
    if raw.shape!=(240,320) or raw.dtype!=np.uint8: raise ValueError('Expected 320x240 GRAY8')
    return (YAREA@raw@XAREA.T/255).astype(np.float32)

def compact(pixels):
    a=np.asarray(pixels)
    return a.reshape(*a.shape[:-2],15,2,15,3).mean(axis=(-3,-1)).reshape(*a.shape[:-2],225)

def history(prefix):
    h=np.zeros((3,7),np.float32)
    for i,action in enumerate(prefix[-3:],start=max(0,3-len(prefix))):
        h[i,int(action)]=1;h[i,6]=1
    return h

class Episode:
    """One serial owner; actions and all resulting tics form one transition."""
    def __init__(self,seed,cost=None):
        if isinstance(seed,bool) or not 0<=int(seed)<2**32: raise ValueError('seed must be uint32')
        self.cost=cost if cost is not None else {}
        self.tmp=tempfile.TemporaryDirectory(prefix='cadence-doom-v2-')
        vzd=engine();self.game=vzd.DoomGame()
        try:
            self.game.load_config(str(Path(vzd.scenarios_path)/'basic.cfg'))
            self.game.set_doom_config_path(str(Path(self.tmp.name)/'vizdoom.ini'))
            self.game.set_window_visible(False);self.game.set_sound_enabled(False)
            self.game.set_mode(vzd.Mode.PLAYER)
            self.game.set_screen_resolution(vzd.ScreenResolution.RES_320X240)
            self.game.set_screen_format(vzd.ScreenFormat.GRAY8)
            self.game.set_available_buttons([vzd.Button.MOVE_LEFT,vzd.Button.MOVE_RIGHT,vzd.Button.ATTACK])
            self.game.set_available_game_variables([])
            for option in ('labels_buffer','depth_buffer','automap_buffer','objects_info','sectors_info'):
                getattr(self.game,'set_'+option+'_enabled')(False)
            self.game.set_render_hud(False);self.game.set_render_weapon(True);self.game.set_render_crosshair(False)
            self.game.set_seed(int(seed));self.game.init()
            self.cost['engine_initializations']=self.cost.get('engine_initializations',0)+1
        except BaseException:
            self.close();raise
    def raw(self):
        state=self.game.get_state()
        return None if state is None else np.array(state.screen_buffer,copy=True)
    def step(self,action,tics=12,kind='evaluation'):
        if isinstance(action,bool) or not isinstance(action,(int,np.integer)) or not 0<=action<6:
            raise ValueError('action must be a declared six-way action ID')
        if not isinstance(tics,int) or tics<1: raise ValueError('tics must be positive')
        if self.game.is_episode_finished(): raise RuntimeError('Action after terminal')
        rewards=[]
        for _ in range(tics):
            rewards.append(float(self.game.make_action(list(ACTIONS[action]),1)))
            self.cost[kind+'_tics']=self.cost.get(kind+'_tics',0)+1
            if self.game.is_episode_finished(): break
        self.cost[kind+'_calls']=self.cost.get(kind+'_calls',0)+1
        return {'reward':sum(rewards),'rewards':rewards,'tics':len(rewards),
                'terminal':bool(self.game.is_episode_finished()),
                'timeout':bool(self.game.is_episode_timeout_reached())}
    def close(self):
        try:self.game.close()
        finally:self.tmp.cleanup()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
