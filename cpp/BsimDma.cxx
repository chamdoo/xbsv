
// Copyright (c) 2013-2014 Quanta Research Cambridge, Inc.

// Permission is hereby granted, free of charge, to any person
// obtaining a copy of this software and associated documentation
// files (the "Software"), to deal in the Software without
// restriction, including without limitation the rights to use, copy,
// modify, merge, publish, distribute, sublicense, and/or sell copies
// of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:

// The above copyright notice and this permission notice shall be
// included in all copies or substantial portions of the Software.

// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
// EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
// MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
// NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
// BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
// ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
// CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

#include <errno.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <assert.h>
#include <stdio.h>
#include <sys/mman.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <pthread.h>

#include "portal.h"
#include "sock_utils.h"

static struct {
    unsigned char *buffer;
    uint32_t buffer_len;
    int size_accum;
} dma_info[32];

extern "C" {
  void write_pareff32(uint32_t pref, uint32_t offset, unsigned int data){
    *(unsigned int *)&dma_info[pref].buffer[offset] = data;
  }

  unsigned int read_pareff32(uint32_t pref, uint32_t offset){
    return *(unsigned int *)&dma_info[pref].buffer[offset];
  }

  void write_pareff64(uint32_t pref, uint32_t offset, uint64_t data){
    *(uint64_t *)&dma_info[pref].buffer[offset] = data;
  }

  uint64_t read_pareff64(uint32_t pref, uint32_t offset){
    return *(uint64_t *)&dma_info[pref].buffer[offset];
  }

  void pareff(uint32_t apref, uint32_t size){
    uint32_t pref = apref >> 8;
    //fprintf(stderr, "BsimDma::pareff pref=%ld, size=%08x size_accum=%08x\n", pref, size, dma_info[pref].size_accum);
    assert(pref < 32);
    dma_info[pref].size_accum += size;
    if(size == 0){
      int fd;
      pareff_fd(&fd);
      dma_info[pref].buffer = (unsigned char *)mmap(0,
          dma_info[pref].size_accum, PROT_WRITE|PROT_WRITE|PROT_EXEC, MAP_SHARED, fd, 0);
      if (dma_info[pref].buffer == MAP_FAILED) {
          printf("%s: mmap failed fd %x buffer %p size %x errno %d\n", __FUNCTION__, fd, dma_info[pref].buffer, size, errno);
          exit(-1);
      }
      dma_info[pref].buffer_len = dma_info[pref].size_accum;
    }
  }
}
