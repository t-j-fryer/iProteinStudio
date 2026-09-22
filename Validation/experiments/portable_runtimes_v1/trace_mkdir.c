/* Diagnostic only: log cache directory creation in our own test subprocess. */
#include <sys/stat.h>
#include <unistd.h>
#include <string.h>
#include <stdio.h>
static void log_path(const char *kind,const char *path) {
 char buf[2048];int n=snprintf(buf,sizeof(buf),"STUDIO_CACHE_TRACE|%s|%s\n",kind,path?path:"(null)");
 if(n>0)write(2,buf,(size_t)n<sizeof(buf)?(size_t)n:sizeof(buf)-1);
}
static int trace_mkdir(const char *path,mode_t mode){log_path("mkdir",path);return mkdir(path,mode);}
static int trace_mkdirat(int fd,const char *path,mode_t mode){log_path("mkdirat",path);return mkdirat(fd,path,mode);}
__attribute__((used)) static struct {const void *replacement;const void *original;} hooks[] __attribute__((section("__DATA,__interpose")))={
 {(const void *)trace_mkdir,(const void *)mkdir},
 {(const void *)trace_mkdirat,(const void *)mkdirat}
};
