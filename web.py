import os, math, tempfile, subprocess, uuid
from flask import Flask, request, send_file, abort, render_template_string, after_this_request

app = Flask(__name__)
MAX_MB = 4096  # basic guard

HTML = """
<!doctype html>
<meta charset="utf-8">
<title>video compressor</title>
<style>
  body{font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:40px}
  .box{border:2px dashed #bbb;border-radius:16px;padding:28px;text-align:center}
  .box.drag{border-color:#000}
  .row{margin-top:16px;display:flex;gap:12px;align-items:center;justify-content:center}
  input[type=number]{width:120px;padding:8px}
  button{padding:10px 16px;border:0;border-radius:10px;background:#111;color:#fff;cursor:pointer}
  small{color:#666}
</style>
<div class="box" id="drop">
  <h2>drag & drop a video here</h2>
  <div>or <label style="text-decoration:underline;cursor:pointer"><input id="file" type="file" name="file" accept="video/*" hidden>click to choose</label></div>
  <div class="row">
    <label>target size (mb): <input id="mb" type="number" min="1" max="4096" value="25"></label>
    <button id="go">compress</button>
  </div>
  <div class="row"><small id="status"></small></div>
</div>
<script>
const drop = document.getElementById('drop');
const fileInput = document.getElementById('file');
const go = document.getElementById('go');
const mb = document.getElementById('mb');
const statusEl = document.getElementById('status');
let file=null;

function setStatus(t){ statusEl.textContent=t; }
['dragenter','dragover'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('drag');}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('drag');}));
drop.addEventListener('drop', ev=>{ file = ev.dataTransfer.files[0]; setStatus(file?`selected: ${file.name}`:''); });
drop.addEventListener('click', ()=>fileInput.click());
fileInput.addEventListener('change', ()=>{ file = fileInput.files[0]; setStatus(file?`selected: ${file.name}`:''); });

go.addEventListener('click', async ()=>{
  if(!file){ setStatus('pick a file'); return; }
  const m = parseInt(mb.value||'0',10);
  if(!(m>0)){ setStatus('enter target size'); return; }
  setStatus('processing… this may take a while');
  const fd = new FormData();
  fd.append('file', file);
  fd.append('target_mb', m.toString());
  try{
    const res = await fetch('/compress', { method:'POST', body:fd });
    if(!res.ok){
      const txt = await res.text();
      setStatus(`error: ${txt || res.status}`);
      return;
    }
    const blob = await res.blob();
    const dispo = res.headers.get('Content-Disposition') || '';
    const m = dispo.match(/filename="(.+?)"/);
    const name = m? m[1] : 'compressed.mp4';
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name; document.body.appendChild(a); a.click();
    URL.revokeObjectURL(url); a.remove();
    setStatus('done');
  }catch(e){ setStatus('error: '+e); }
});
</script>
"""

def _have(cmd):
    return subprocess.call(['which', cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)==0

def _ffprobe_duration(path):
    try:
        out = subprocess.check_output([
            'ffprobe','-v','error','-show_entries','format=duration',
            '-of','default=noprint_wrappers=1:nokey=1', path
        ], stderr=subprocess.DEVNULL).decode().strip()
        return float(out)
    except Exception:
        return 0.0

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/compress", methods=["POST"])
def compress():
    if not _have('ffprobe') or not _have('ffmpeg'):
        return abort(500, "ffprobe/ffmpeg not found")
    f = request.files.get('file')
    t = request.form.get('target_mb','').strip()
    if not f or not t.isdigit():
        return abort(400, "missing file or target_mb")
    target_mb = int(t)
    if target_mb<=0 or target_mb>MAX_MB:
        return abort(400, "invalid target_mb")
    # save upload
    tmpdir = tempfile.mkdtemp(prefix="vc_")
    inpath = os.path.join(tmpdir, f"{uuid.uuid4()}.{(f.filename or 'in').split('.')[-1]}")
    f.save(inpath)
    dur = _ffprobe_duration(inpath)
    if dur<=0:
        return abort(400, "unable to read duration")
    # compute bitrate_k (no audio), minus 5% container overhead
    bytes_per_mb = 1048576
    size_bits = target_mb * bytes_per_mb * 8
    usable_bits = int(size_bits * 0.95)
    bitrate_bps = max(1, usable_bits // int(math.ceil(dur)))
    bitrate_k = max(1, bitrate_bps // 1024)
    # output
    base = os.path.splitext(os.path.basename(f.filename or "video"))[0] or "video"
    outpath = os.path.join(tmpdir, f"{base}_compressed.mp4")
    cmd = ['ffmpeg','-y','-i', inpath, '-c:v','libx265','-b:v', f'{bitrate_k}k','-an', outpath]
    try:
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        return abort(500, f"ffmpeg failed: {e.returncode}")

    @after_this_request
    def cleanup(resp):
        try:
            if os.path.exists(inpath): os.remove(inpath)
            # keep outpath until send finishes; temp dir will be removed by system later
        except Exception:
            pass
        return resp

    return send_file(outpath, as_attachment=True, download_name=os.path.basename(outpath), mimetype='video/mp4')

if __name__ == "__main__":
    app.run(debug=True)
