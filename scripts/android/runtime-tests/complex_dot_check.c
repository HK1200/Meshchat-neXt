#include <complex.h>
#include <dlfcn.h>
#include <math.h>
#include <stdio.h>
int main(int argc,char**argv) {
 if(argc!=2)return 2;
 void* lib=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);
 if(!lib){fprintf(stderr,"%s\n",dlerror());return 3;}
 typedef float complex(*cfun)(int*,float complex*,int*,float complex*,int*);
 typedef double complex(*zfun)(int*,double complex*,int*,double complex*,int*);
 cfun c=(cfun)dlsym(lib,"cdotc_");zfun z=(zfun)dlsym(lib,"zdotc_");
 if(!c||!z)return 4;
 int n=2,inc=1;float complex cx[]={1+2*I,3+4*I},cy[]={5+6*I,7+8*I};
 double complex zx[]={1+2*I,3+4*I},zy[]={5+6*I,7+8*I};
 float complex cr=c(&n,cx,&inc,cy,&inc);double complex zr=z(&n,zx,&inc,zy,&inc);
 if(cabsf(cr-(70-8*I))>1e-5f||cabs(zr-(70-8*I))>1e-10){fprintf(stderr,"complex return mismatch\n");return 5;}
 puts("PASS: Fortran single/double complex dot return ABI");return 0;
}
