package com.meshchatnext;
import android.app.Instrumentation;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.PowerManager;
import android.util.Log;
import com.chaquo.python.Python;
import com.chaquo.python.PyObject;
import com.chaquo.python.android.AndroidPlatform;
import java.io.*;
import java.nio.charset.StandardCharsets;

public class NumpyInstrumentation extends Instrumentation {
    private String mode;
    private Bundle arguments;
    @Override public void onCreate(Bundle args) { arguments=args; mode=args==null?"bindings":args.getString("mode","bindings");start(); }
    private void removeGenerated(File file) throws IOException {
        if(!file.exists() && !java.nio.file.Files.isSymbolicLink(file.toPath())) return;
        if(!java.nio.file.Files.isSymbolicLink(file.toPath()) && file.isDirectory()) {
            File[] children=file.listFiles();
            if(children != null) for(File child:children) removeGenerated(child);
        }
        if(!file.delete()) throw new IOException("Could not remove generated test cache");
    }
    @Override public void onStart() {
        Bundle result=new Bundle();
        PowerManager.WakeLock wakeLock=null;
        try {
            Context target=getTargetContext();
            PowerManager power=(PowerManager)target.getSystemService(Context.POWER_SERVICE);
            wakeLock=power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"Meshchat neXt:numerical-tests");
            wakeLock.setReferenceCounted(false);
            // A locked physical phone may otherwise suspend mid-suite. Bound the
            // hold even if a test stalls; process death also releases this lock.
            wakeLock.acquire(45L*60L*1000L);
            // Instrumentation.start can run before Application.onCreate.
            // Let the target PyApplication initialize its own Python first.
            waitForIdleSync();
            if(arguments != null && "true".equals(arguments.getString("foreground","false"))) {
                Intent intent=new Intent();intent.setClassName(target.getPackageName(),"com.meshchatnext.NumpyTestActivity");intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                startActivitySync(intent);
            }
            if(mode.equals("cleanup")) {
                removeGenerated(new File(target.getCacheDir(),"numpy-runtime-tests"));
                File diagnosticDirectory=target.getExternalFilesDir(null);
                if(diagnosticDirectory != null) removeGenerated(new File(diagnosticDirectory,"numpy-test-stall-trace.txt"));
                File legacy=new File(target.getCacheDir(),"chaquopy/tmp");
                File[] files=legacy.listFiles();
                if(files != null) for(File file:files) {
                    String name=file.getName();
                    if(name.startsWith("pytest-of-") || name.startsWith("numpy_test_big_arrays_")) removeGenerated(file);
                }
                result.putString("cleanup","Generated numerical-test cache removed; app files retained");
                finish(Activity.RESULT_OK,result);return;
            }
            if(mode.equals("report")) {
                String name=arguments.getString("file","numpy-upstream-results.json");
                if(!name.equals("numpy-upstream-results.json") && !name.equals("numpy-upstream.xml") && !name.equals("numpy-upstream-output.txt")) throw new IllegalArgumentException("Unexpected report");
                byte[] data=java.nio.file.Files.readAllBytes(new File(target.getCacheDir(),"numpy-runtime-tests/"+name).toPath());
                int offset=Integer.parseInt(arguments.getString("offset","0"));
                int size=Math.min(49152,data.length-offset);
                result.putString("total",Integer.toString(data.length));
                result.putString("chunk",android.util.Base64.encodeToString(java.util.Arrays.copyOfRange(data,offset,offset+size),android.util.Base64.NO_WRAP));
                finish(Activity.RESULT_OK,result);return;
            }
            if(!Python.isStarted()) throw new IllegalStateException("Target application did not initialize Python");
            Python python=Python.getInstance();
            PyObject globals=python.getBuiltins().callAttr("dict");
            globals.callAttr("__setitem__","TEST_MODE",mode);
            globals.callAttr("__setitem__","TRACE_TESTS",arguments != null && "true".equals(arguments.getString("trace","false")));
            if(arguments != null && arguments.containsKey("tests")) {
                globals.callAttr("__setitem__","SELECTED_TESTS",new String(android.util.Base64.decode(arguments.getString("tests"),android.util.Base64.DEFAULT),StandardCharsets.UTF_8));
            }
            globals.callAttr("__setitem__","TEST_ROOT",new File(target.getCacheDir(),"numpy-runtime-tests").getAbsolutePath());
            File external=target.getExternalFilesDir(null);
            if(external != null) globals.callAttr("__setitem__","TEST_DIAGNOSTIC_FILE",new File(external,"numpy-test-stall-trace.txt").getAbsolutePath());
            File root=new File(target.getCacheDir(),"numpy-runtime-tests");root.mkdirs();
            for(String name:getContext().getAssets().list("runtime-deps")) {
                try(InputStream in=getContext().getAssets().open("runtime-deps/"+name);FileOutputStream out=new FileOutputStream(new File(root,name))) {
                    byte[] b=new byte[16384];int n;while((n=in.read(b))!=-1)out.write(b,0,n);
                }
            }
            String script=mode.equals("bindings")?"numpy_runtime.py":"numpy_full_suite.py";
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            try(InputStream in=getContext().getAssets().open(script)) {
                byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1)bytes.write(b,0,n);
            }
            python.getBuiltins().callAttr("exec",bytes.toString(StandardCharsets.UTF_8.name()),globals);
            String summary=globals.callAttr("__getitem__","RESULT").toString();
            result.putString("summary",summary);Log.i("MeshchatNextNumpyTest",summary);
            finish(Activity.RESULT_OK,result);
        } catch(Throwable e) {
            Log.e("MeshchatNextNumpyTest","Numerical test failed",e);
            result.putString("failure",e.toString());finish(Activity.RESULT_CANCELED,result);
        } finally {
            if(wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        }
    }
}
