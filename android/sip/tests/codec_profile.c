/* SPDX-License-Identifier: 0BSD */
/* Exercises the real codec registry and Opus encoder/decoder, without devices. */
#include <re.h>
#include <rem.h>
#include <baresip.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "mobile_sip_audio.h"
#ifdef LEGACY_STEREO_PROFILE
#undef MOBILE_SIP_OPUS_CONFIG
#undef MOBILE_SIP_AUDIO_CODECS
#define MOBILE_SIP_OPUS_CONFIG "opus_stereo yes\nopus_sprop_stereo yes\n"
#define MOBILE_SIP_AUDIO_CODECS "opus/48000/2,PCMU/8000/1,PCMA/8000/1"
#endif
int main(void) {
 int err=libre_init();struct account *account=NULL;struct auenc_state *enc=NULL;struct audec_state *dec=NULL;
 if(err)return 1;
 const char *config=MOBILE_SIP_OPUS_CONFIG;
 if((err=conf_configure_buf((const uint8_t *)config,strlen(config))) || (err=baresip_init(conf_config())) ||
    (err=module_preload("opus")) || (err=module_preload("g711")))goto done;
 err=account_alloc(&account,"<sip:private-codec-test@127.0.0.1>;regint=0;audio_codecs=" MOBILE_SIP_AUDIO_CODECS);
 if(err)goto done;
 const struct aucodec *ac=aucodec_find(account_aucodecl(account),"opus",48000,0);
 if(!ac || ac->ch!=1 || ac->pch!=2 || !aucodec_find(account_aucodecl(account),"PCMU",8000,1)) {
  fprintf(stderr,"Mobile SIP must retain mono Opus, standard RTP /2 and G.711 fallback\n");err=1;goto done;
 }
 struct auenc_param prm={.bitrate=32000};
 if((err=ac->encupdh(&enc,ac,&prm,ac->fmtp)) || (err=ac->decupdh(&dec,ac,ac->fmtp)))goto done;
 int16_t input[960],output[2880];for(int i=0;i<960;i++)input[i]=(int16_t)((i%80-40)*120);
 uint8_t packet[2000];size_t len=sizeof(packet),count=2880;bool marker=false;
 if((err=ac->ench(enc,&marker,packet,&len,AUFMT_S16LE,input,960)))goto done;
 if(!len){err=1;goto done;}
 if((err=ac->dech(dec,AUFMT_S16LE,output,&count,false,packet,len)))goto done;
 int audible=0;for(size_t i=0;i<count;i++)if(output[i]>100 || output[i]<-100)audible=1;
 if(count!=960 || !audible){err=1;goto done;}
 puts("Mono Opus account selection and 48 kHz speech round-trip passed; RTP /2 and G.711 retained");
 done:
 mem_deref(enc);mem_deref(dec);mem_deref(account);baresip_close();conf_close();mod_close();libre_close();
 if(err)fprintf(stderr,"SIP codec regression failed (%d)\n",err);
 return err?1:0;
}
