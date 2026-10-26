package com.meshchatnext;
import android.app.Activity;
import android.os.Bundle;
import android.os.Build;
import android.view.WindowManager;
import android.widget.TextView;
/** Opt-in diagnostic target only; absent from normal release APKs. */
public class NumpyTestActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if(Build.VERSION.SDK_INT >= 27) {setShowWhenLocked(true);setTurnScreenOn(true);}
        else getWindow().addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
        setTitle("Numerical validation");
        TextView text=new TextView(this);text.setText("Numerical validation is running.\nYou can leave this screen open.");text.setTextSize(20);text.setPadding(32,64,32,32);setContentView(text);
    }
}
