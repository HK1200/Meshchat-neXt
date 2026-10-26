package com.meshchatnext;

import org.junit.After;
import org.junit.Assert;
import org.junit.Test;

/**
 * Trusted call-notification actions must not be forgeable via exported MainActivity.
 */
public class CallNotificationTrustedActionTest {

    @After
    public void tearDown() {
        AndroidNotificationBridge.clearTrustedCallActionForTests();
        AndroidNotificationBridge.setMeshCoreUiForeground(false);
        AndroidNotificationBridge.setOpenConversationHashes("");
    }

    @Test
    public void messageNotificationLinksKeepNetworkDestinationsSeparate() {
        String peer = "0123456789abcdef0123456789abcdef";
        String key = "meshcore-" + peer + peer;
        Assert.assertEquals("meshchatnext://app/meshcore?notification=" + key, AndroidNotificationBridge.messageOpenUri(key));
        Assert.assertEquals("meshchatnext://app/messages?destination=" + peer, AndroidNotificationBridge.messageOpenUri(peer));
        Assert.assertEquals("meshchatnext://app/messages", AndroidNotificationBridge.messageOpenUri("invalid/?target=other"));
    }

    @Test
    public void meshCoreOpenContextDoesNotSuppressAlertsAfterBackgrounding() {
        AndroidNotificationBridge.setOpenConversationHashes("meshcore-example,rns-peer");
        AndroidNotificationBridge.setMeshCoreUiForeground(true);
        Assert.assertTrue(AndroidNotificationBridge.isMeshCoreConversationOpen("meshcore-example"));
        AndroidNotificationBridge.setMeshCoreUiForeground(false);
        Assert.assertFalse(AndroidNotificationBridge.isMeshCoreConversationOpen("meshcore-example"));
        Assert.assertTrue(AndroidNotificationBridge.isOpenConversationHash("rns-peer"));
    }

    @Test
    public void mapCallNotificationActionRecognizesAnswerDeclineOpen() {
        Assert.assertEquals(
            AndroidNotificationBridge.TRUSTED_CALL_ACTION_ANSWER,
            AndroidNotificationBridge.mapCallNotificationAction(
                AndroidNotificationBridge.ACTION_CALL_ANSWER
            )
        );
        Assert.assertEquals(
            AndroidNotificationBridge.TRUSTED_CALL_ACTION_DECLINE,
            AndroidNotificationBridge.mapCallNotificationAction(
                AndroidNotificationBridge.ACTION_CALL_DECLINE
            )
        );
        Assert.assertEquals(
            AndroidNotificationBridge.TRUSTED_CALL_ACTION_OPEN,
            AndroidNotificationBridge.mapCallNotificationAction(
                AndroidNotificationBridge.ACTION_CALL_OPEN
            )
        );
        Assert.assertNull(AndroidNotificationBridge.mapCallNotificationAction(null));
        Assert.assertNull(AndroidNotificationBridge.mapCallNotificationAction("android.intent.action.VIEW"));
        Assert.assertNull(
            AndroidNotificationBridge.mapCallNotificationAction("com.meshchatnext.action.CALL_ATTACK")
        );
    }

    @Test
    public void offerAndTakeTrustedCallActionIsOneShot() {
        AndroidNotificationBridge.offerTrustedCallAction(
            AndroidNotificationBridge.TRUSTED_CALL_ACTION_ANSWER
        );
        Assert.assertEquals(
            AndroidNotificationBridge.TRUSTED_CALL_ACTION_ANSWER,
            AndroidNotificationBridge.takeTrustedCallAction()
        );
        Assert.assertNull(AndroidNotificationBridge.takeTrustedCallAction());
    }

    @Test
    public void offerTrustedCallActionRejectsUnknownTokens() {
        AndroidNotificationBridge.offerTrustedCallAction("initiate");
        AndroidNotificationBridge.offerTrustedCallAction("");
        AndroidNotificationBridge.offerTrustedCallAction(null);
        Assert.assertNull(AndroidNotificationBridge.takeTrustedCallAction());
    }

    @Test
    public void latestTrustedCallActionWins() {
        AndroidNotificationBridge.offerTrustedCallAction(
            AndroidNotificationBridge.TRUSTED_CALL_ACTION_ANSWER
        );
        AndroidNotificationBridge.offerTrustedCallAction(
            AndroidNotificationBridge.TRUSTED_CALL_ACTION_DECLINE
        );
        Assert.assertEquals(
            AndroidNotificationBridge.TRUSTED_CALL_ACTION_DECLINE,
            AndroidNotificationBridge.takeTrustedCallAction()
        );
    }
}
