"""Private-bus end-to-end check: MPRIS, imported lyrics, native rendering and Escape."""
import os,sys,tempfile,subprocess,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version("Gtk","3.0")
gi.require_version("Gdk","3.0")
from gi.repository import GLib,Gdk
from afterglow.app import AfterglowApp,DEMO_LRC
from afterglow.storage import resolve_lyrics
tmp=tempfile.TemporaryDirectory()
os.environ["XDG_CONFIG_HOME"]=tmp.name+"/config"
os.environ["XDG_CACHE_HOME"]=tmp.name+"/cache"
track=dict(title="First Light",artist="Afterglow",album="Original Fixtures",duration=30.0,track_url="afterglow:fixture")
resolve_lyrics(track,DEMO_LRC)
proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name("mpris_fixture.py"))])
app=AfterglowApp(demo=False)
errors=[]
limit=time.monotonic()+8
def check():
 if not app.playback or app.document.quality!="word":
  if time.monotonic()<limit:return True
  errors.append(AssertionError("Player to cached-lyrics flow timed out"));app.quit();return False
 try:
  assert app.playback.name=="Afterglow Fixture"
  assert app.document.lines[0].text=="Let the room glow"
  old=app.generation.generation
  original=app.document
  app.generation.next()
  from afterglow.lyrics import LyricDocument
  app.content_ready("lyrics",old,LyricDocument(),"")
  assert app.document is original,"stale result replaced current lyrics"
  app.show_visual("fullscreen")
  class Event:keyval=Gdk.KEY_Escape
  assert app.visual.key(None,Event())
  assert app.visual is None and app.window.get_visible()
  print("Connected MPRIS → local imported lyrics → native scene; stale result ignored; Escape handler: PASS")
 except Exception as e:errors.append(e)
 app.quit();return False
GLib.timeout_add(100,check)
try:
 app.run(["afterglow-connected-check"])
 assert not errors,errors
finally:
 proc.terminate();proc.wait(timeout=3)
 tmp.cleanup()
