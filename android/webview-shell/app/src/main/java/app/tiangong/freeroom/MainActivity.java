package app.tiangong.freeroom;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.TextView;
import android.view.View;

/**
 * 一个只做一件事的壳：用系统 WebView 打开空教室站点。
 *
 * 为什么不用 TWA：TWA 要隐藏地址栏必须先向 Google 的归属校验服务查询，
 * 且渲染依赖手机上装了 Chrome；国内机型上这两条任意一条不满足就会卡在启动屏。
 * 直壳没有这些依赖，代价只是少了 TWA 的"受信任"标记 —— 对用户无感。
 *
 * 内容与网页完全同源：这里加载的就是网站本身，每天 06:00 的抓取结果两边同时生效，
 * 改网页不需要重新发版。
 */
public class MainActivity extends Activity {

    private static final String START_URL =
            "https://zhenbinping-boop.github.io/tiangong-free-room/index.html";
    private static final String OWN_HOST = "zhenbinping-boop.github.io";

    private WebView web;
    private View errorView;

    private final WebViewClient client = new WebViewClient() {

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri uri = request.getUrl();
            if (OWN_HOST.equals(uri.getHost())) {
                return false; // 站内链接继续在本壳里打开
            }
            // 站外链接交给系统浏览器，壳只负责本站
            Intent intent = new Intent(Intent.ACTION_VIEW, uri);
            if (intent.resolveActivity(getPackageManager()) != null) {
                startActivity(intent);
            }
            return true;
        }

        @Override
        public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
            showError(null);
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request.isForMainFrame()) {
                showError(getString(R.string.error_desc));
            }
        }
    };

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        web = findViewById(R.id.web);
        errorView = findViewById(R.id.error_view);
        Button retry = findViewById(R.id.retry);
        TextView desc = findViewById(R.id.error_desc);
        desc.setText(R.string.error_desc);
        retry.setOnClickListener(v -> {
            showError(null);
            web.reload();
        });

        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        // 每次打开都走网络，缓存只在断网时兜底 —— 这个站的全部价值是"今天的数据"
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setLoadWithOverviewMode(false);
        settings.setSupportZoom(true);
        settings.setBuiltInZoomControls(true);
        settings.setDisplayZoomControls(false);

        web.setWebViewClient(client);

        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState);
        } else {
            web.loadUrl(START_URL);
        }
    }

    private void showError(String message) {
        if (errorView == null) return;
        if (message == null) {
            errorView.setVisibility(View.GONE);
        } else {
            errorView.setVisibility(View.VISIBLE);
        }
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onPause() {
        if (web != null) web.onPause();
        super.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) web.onResume();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        if (web != null) web.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.setWebViewClient(new WebViewClient());
            web.destroy();
        }
        super.onDestroy();
    }
}
