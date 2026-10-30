"""Rebuild the two 29.5s sound edits without re-encoding the picture.

python mix.py --assets /private/audio-cache --output /private/renders
Requires FFmpeg, numpy, scipy and soundfile. Original stock files and WAV
intermediates belong in a private cache, not this public repository.
"""
from pathlib import Path
import argparse, hashlib, json, math, os, re, shutil, subprocess, urllib.request
import numpy as np
import soundfile as sf
from scipy import signal

ROOT = Path(__file__).resolve().parent
VIDEO = ROOT.parent.parent
SR = 48000
DURATION = 29.5
N = int(SR * DURATION)
RNG = np.random.default_rng(1438)

def executable(name):
    found = shutil.which(name)
    if found: return found
    winget = Path.home() / 'AppData/Local/Microsoft/WinGet/Packages'
    candidates = sorted(winget.glob(f'Gyan.FFmpeg*/**/{name}.exe'))
    if not candidates: raise RuntimeError(f'{name} is required; add FFmpeg to PATH')
    return str(candidates[-1])

FF = executable('ffmpeg')
PROBE = executable('ffprobe')

def run(args):
    return subprocess.run(args, check=True, capture_output=True)

def decode(path, filters=None):
    args=[FF,'-v','error','-i',str(path)]
    if filters:args += ['-af',filters]
    return np.frombuffer(run(args+['-f','f32le','-ar',str(SR),'-ac','2','-']).stdout,np.float32).reshape(-1,2).copy()

def amp(db):return 10 ** (db/20)

def ramp(points, count=N):
    t=np.arange(count)/SR
    return np.interp(t,[p[0] for p in points],[p[1] for p in points])

def fade(a, fi=.005, fo=.06):
    a=a.copy()
    ni=min(int(fi*SR),len(a));no=min(int(fo*SR),len(a))
    if ni:a[:ni] *= np.sin(np.linspace(0,np.pi/2,ni))[:,None]**2
    if no:a[-no:] *= np.cos(np.linspace(0,np.pi/2,no))[:,None]**2
    return a

def filt(a,hp=45,lp=15000):
    if hp:a=signal.sosfilt(signal.butter(2,hp,fs=SR,btype='highpass',output='sos'),a,axis=0)
    if lp:a=signal.sosfilt(signal.butter(2,lp,fs=SR,btype='lowpass',output='sos'),a,axis=0)
    return a

def place(dst,clip,time):
    start=round(time*SR);skip=max(0,-start);start=max(0,start)
    length=min(len(clip)-skip,len(dst)-start)
    if length>0:dst[start:start+length]+=clip[skip:skip+length]

def peak_level(a,db):
    return a*(amp(db)/max(float(np.max(np.abs(a))),1e-9))

def stereo_pan(a,pan):
    # Keep some source width, with equal-power object positioning.
    mid=a.mean(axis=1)
    side=(a[:,0]-a[:,1])*.12
    ang=(pan+1)*np.pi/4
    return np.column_stack([mid*np.cos(ang)+side,mid*np.sin(ang)-side])*np.sqrt(2)

def pluck(midi,length=1.2):
    t=np.arange(int(SR*length))/SR;f=440*2**((midi-69)/12)
    # Damped, slightly inharmonic tine and mallet attack, with real decay.
    mono=(np.sin(2*np.pi*f*t)*np.exp(-t*5)
          +.32*np.sin(2*np.pi*f*2.003*t)*np.exp(-t*12)
          +.14*np.sin(2*np.pi*f*3.998*t)*np.exp(-t*20))
    mono*=np.minimum(t/.002,1)
    a=np.column_stack([mono,mono])
    dry=a.copy()
    for delay,gain in [(.047,.13),(.083,.10),(.127,.065),(.193,.035)]:
        shift=int(delay*SR)
        a[shift:]+=dry[:-shift,::-1]*gain
    return fade(a,fo=.18)

def body(length=.45,freq=100):
    t=np.arange(int(SR*length))/SR
    f=freq*np.exp(-t*13)+48
    wave=np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-t*12)
    return fade(np.column_stack([wave,wave]),.002,.12)

def source_clip(cue,assets,sources):
    sid=str(cue['asset'])
    if sid=='pluck':a=pluck(cue['note'],cue.get('duration',1.2))
    elif sid=='body':a=body(cue.get('duration',.45),cue.get('freq',100))
    else:
        a=decode(assets/sources[sid]['filename'])
        active=np.where(np.max(abs(a),axis=1)>np.max(abs(a))*.008)[0]
        if len(active):a=a[max(0,active[0]-int(.003*SR)):min(len(a),active[-1]+int(.07*SR))]
        if 'crop' in cue:a=a[int(cue['crop'][0]*SR):int(cue['crop'][1]*SR)]
        ratio=2**(cue.get('pitch',0)/12)*cue.get('speed',1)
        if ratio!=1:a=signal.resample(a,max(8,round(len(a)/ratio)))
        a=filt(a,cue.get('hp',80),cue.get('lp',12000))
        a=fade(a,.002,min(.08,len(a)/SR/4))
    a=stereo_pan(a,cue.get('pan',0))
    a=peak_level(a,cue['db'])
    if cue.get('reverse'):a=a[::-1].copy()
    offset=0
    if cue.get('anchor')=='peak':offset=int(np.argmax(np.max(abs(a),axis=1)))/SR
    return a,offset

def prepare_assets(assets,manifest):
    assets.mkdir(parents=True,exist_ok=True)
    for x in manifest['assets']:
        p=assets/x['filename']
        if not p.exists():
            req=urllib.request.Request(x['download_url'],headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=60) as response:p.write_bytes(response.read())
        sha=hashlib.sha256(p.read_bytes()).hexdigest()
        if sha!=x['sha256']:raise RuntimeError(f'Asset checksum changed: {p.name}')

def music_edit(plan,assets):
    music=plan['music']
    a=decode(assets/music['filename'],f"atempo={music['tempo']},highpass=f=35,lowpass=f=15000")
    # Stable gain; preserve internal groove dynamics, never normalize each beat.
    a*=.115/max(float(np.sqrt(np.mean(a[int(SR*5):int(SR*25)]**2))),1e-8)
    bed=np.zeros((N,2))
    for edit in music['edits']:
        start=round(edit['source']/music['tempo']*SR)
        count=round(edit['length']*SR)
        clip=a[start:start+count]
        clip=fade(clip,edit.get('fade_in',.012),edit.get('fade_out',.08))
        place(bed,clip,edit['at'])
    bed*=ramp(music['gain'])[:,None]
    if 'lowpass_blend' in music:
        muffled=filt(bed,30,700)
        amount=ramp(music['lowpass_blend'])[:,None]
        bed=bed*(1-amount)+muffled*amount
    return bed

def mix_one(key,plan,assets,out,sources):
    bed=music_edit(plan,assets)
    foley=np.zeros_like(bed); accents=np.zeros_like(bed)
    cue_report=[];duck=np.ones(N)
    for cue in plan['cues']:
        clip,offset=source_clip(cue,assets,sources)
        start=cue['at']-offset
        place(foley if cue.get('bus')=='foley' else accents,clip,start)
        cue_report.append(dict(cue,start=round(start,5),length=round(len(clip)/SR,5)))
        if cue.get('duck'):
            t=cue['at'];d=amp(-cue['duck'])
            env=ramp([[0,1],[max(0,t-.07),1],[t,d],[t+.12,d],[t+.38,1],[DURATION,1]])
            duck=np.minimum(duck,env)
    bed*=duck[:,None]
    # Subtle continuous texture represents motion, gated when the balls stop.
    if key=='B':
        t=np.arange(N)/SR
        noise=RNG.normal(0,1,(N,2))
        roll=filt(noise,150,650)
        mod=.7+.18*np.sin(t*31)+.12*np.sin(t*53)
        roll*=mod[:,None]
        roll=peak_level(roll,-32)
        roll*=ramp([[0,0],[.3,.4],[2.3,.5],[3,.1],[5.4,.1],[6.5,.65],[10.9,.55],[11.6,.12],[11.9,.2],[12.35,0],[14.5,0],[14.7,.5],[15.05,.8],[20.6,.2],[21.4,0],[29.5,0]])[:,None]
        foley+=roll
    raw=bed+foley+accents
    raw=fade(raw,.01,.16)
    for name,stem in [('music',bed),('foley',foley),('accents',accents),('premaster',raw)]:
        sf.write(out/f'{key}-{name}.wav',stem,SR,subtype='FLOAT')
    wav=out/f'{key}-premaster.wav'
    first=run([FF,'-hide_banner','-i',str(wav),'-af','loudnorm=I=-15:TP=-1.5:LRA=9:print_format=json','-f','null','-']).stderr.decode()
    measured=json.loads(re.findall(r'\{[^{}]+\}',first)[-1])
    filtstr=(f"loudnorm=I=-15:TP=-1.5:LRA=9:measured_I={measured['input_i']}:"
             f"measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:"
             f"measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true:print_format=json")
    master=out/f'{key}-master.wav'
    run([FF,'-y','-v','error','-i',str(wav),'-af',filtstr,'-ar',str(SR),'-c:a','pcm_s24le',str(master)])
    video=VIDEO/plan['video']
    target=out/plan['video']
    run([FF,'-y','-v','error','-i',str(video),'-i',str(master),'-map','0:v:0','-map','1:a:0',
         '-c:v','copy','-c:a','aac','-b:a','320k','-ar',str(SR),'-t',str(DURATION),
         '-movflags','+faststart','-metadata:s:a:0','title=Music and sound design','-disposition:a:0','default',str(target)])
    # Audit the delivered AAC, not only the floating-point session.
    audit=run([FF,'-hide_banner','-i',str(target),'-vn','-af','loudnorm=I=-15:TP=-1.5:LRA=9:print_format=json','-f','null','-']).stderr.decode()
    loudness=json.loads(re.findall(r'\{[^{}]+\}',audit)[-1])
    def video_hash(path):
        return run([FF,'-v','error','-i',str(path),'-map','0:v:0','-c:v','copy','-f','hash','-hash','sha256','-']).stdout.decode().strip()
    before=video_hash(video);after=video_hash(target)
    if before!=after:raise RuntimeError('Picture stream was changed')
    decoded=decode(target)
    peak=float(np.max(abs(decoded)))
    mono=decoded.mean(axis=1)
    corr=float(np.corrcoef(decoded.T)[0,1])
    mono_ratio=float(np.sqrt(np.mean(mono**2))/np.sqrt(np.mean(decoded**2)))
    probe=json.loads(run([PROBE,'-v','error','-show_streams','-show_format','-of','json',str(target)]).stdout)
    # No unintended gaps. B's deliberate dramatic dip is documented separately.
    rms=[round(20*np.log10(max(float(np.sqrt(np.mean(decoded[i:i+SR//4]**2))),1e-9)),2) for i in range(0,len(decoded),SR//4)]
    report={'plan':key,'file':plan['video'],'loudness':loudness,'video_unchanged':before==after,
            'video_sha256':before,'sample_peak_dbfs':20*np.log10(peak),'stereo_correlation':corr,
            'mono_rms_ratio':mono_ratio,'rms_quarter_seconds_dbfs':rms,'probe':probe,'cues':cue_report}
    (out/f'{key}-qc.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    if not (-15.8<float(loudness['input_i'])<-14.2):raise RuntimeError('Loudness outside delivery window')
    if float(loudness['input_tp'])>-.9:raise RuntimeError('AAC true peak too high')
    if mono_ratio<.75:raise RuntimeError('Mono compatibility failed')
    print(key,{'LUFS':loudness['input_i'],'dBTP':loudness['input_tp'],'picture_unchanged':True,'cues':len(cue_report)})

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--assets',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    public_repo=VIDEO.parent.resolve()
    if args.assets.resolve().is_relative_to(public_repo) or args.output.resolve().is_relative_to(public_repo):
        raise ValueError('Keep original stock audio and WAV intermediates outside the public repository')
    args.output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ROOT/'sources.json').read_text(encoding='utf8'))
    plans=json.loads((ROOT/'timeline.json').read_text(encoding='utf8'))
    prepare_assets(args.assets,manifest)
    sources={str(x['id']):x for x in manifest['assets']}
    for key,plan in plans.items():mix_one(key,plan,args.assets,args.output,sources)

if __name__=='__main__':main()
