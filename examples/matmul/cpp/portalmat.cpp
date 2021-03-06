
// Copyright (c) 2014 Quanta Research Cambridge, Inc.

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

#include <unistd.h>
#include "portalmat.h"
#include <StdDmaIndication.h>

PortalMatAllocator *matAllocator = 0;
sem_t mul_sem;

void PortalMatAllocator::allocate(int dims, const int* sizes, int type, int*& refcount,
				  uchar*& datastart, uchar*& data, size_t* step)
{
  size_t arraysize = step[0]*sizes[0];
  size_t totalsize = cv::alignSize(arraysize+4*sizeof(int), 4096);
  int arraynum = numarrays++;
  arrayFds[arraynum] = portalAlloc(totalsize);

  data = datastart = (uchar*)(unsigned int *)portalMmap(arrayFds[arraynum], totalsize);
  refcount = (int*)(data + arraysize);
  int *parraynum = refcount+1;
  *parraynum = arraynum;
  int *pref = refcount+2;
  *pref = 0;
  int *psize = refcount+3;
  *psize = totalsize;
  *refcount = 1;
  fprintf(stderr, "PortalMatAllocator::allocate   datastart=%p arraynum=%d size=%ld\n",
	  datastart, arraynum, (long)totalsize);
}

void PortalMatAllocator::deallocate(int* refcount, uchar* datastart, uchar* data)
{
  int *parraynum = refcount+1;
  int *pref = refcount+2;
  int *psize = refcount+3;
  int arraynum = *parraynum;
  int ref = *pref;
  size_t totalsize = *psize;
  fprintf(stderr, "PortalMatAllocator::deallocate datastart=%p arraynum=%d size=%ld\n",
	  datastart, arraynum, (long)totalsize);
  munmap(datastart, totalsize);
  close(arrayFds[arraynum]);
}

int PortalMatAllocator::reference(int* refcount, uchar* datastart, uchar* data)
{
  int *parraynum = refcount+1;
  int *pref = refcount+2;
  int arraynum = *parraynum;
  int ref = *pref;
  //fprintf(stderr, "PortalMatAllocator::reference datastart=%p arraynum=%d ref=%d\n", datastart, arraynum, ref);
  if (!ref) {
    //fprintf(stderr, "Calling dma->reference arraynum=%d\n", arraynum);
    ref = dma->reference(arrayFds[arraynum]);
    *pref = ref;
  }
  return ref;
}

PortalMat::PortalMat()
    : cv::Mat() 
{
    allocator = matAllocator;
    fprintf(stderr, "PortalMat::PortalMat() this=%p datastart=%p\n", this, datastart);
}

PortalMat::PortalMat(int rows, int cols, int type)
    : cv::Mat()
{
    allocator = matAllocator;
    create(rows, cols, type);
    fprintf(stderr, "PortalMat::PortalMat(rows,cols) this=%p datastart=%p\n", this, datastart);
}

PortalMat::PortalMat(int rows, int cols, int type, const cv::Scalar& s)
    : cv::Mat()
{
    allocator = matAllocator;
    create(rows, cols, type);
    *(cv::Mat*)this = s;
    fprintf(stderr, "PortalMat::PortalMat(Scalar&) this=%p datastart=%p\n", this, datastart);
}

PortalMat::PortalMat(const PortalMat &m)
  : Mat()
{
    allocator = matAllocator;
    create(m.rows, m.cols, CV_32F);
    //*(cv::Mat*)this = m;
    for (int i = 0; i < m.rows; i++)
	for (int j = 0; j < m.cols; j++) {
	    this->at<float>(i,j) = m.at<float>(i,j);
	}
    fprintf(stderr, "PortalMat::PortalMat(PortalMat&) this=%p datastart=%p\n", this, datastart);
}

PortalMat::PortalMat(const cv::Mat &m)
    : Mat()
{
    allocator = matAllocator;
    create(m.rows, m.cols, CV_32F);
    //*(cv::Mat*)this = m;
    for (int i = 0; i < m.rows; i++)
	for (int j = 0; j < m.cols; j++) {
	    this->at<float>(i,j) = m.at<float>(i,j);
	}
    fprintf(stderr, "PortalMat::PortalMat(Mat&) this=%p datastart=%p\n", this, datastart);
}

PortalMat::~PortalMat() {}

PortalMat& PortalMat::operator = (const cv::MatExpr& expr)
{
    *(cv::Mat*)this = expr;
    fprintf(stderr, "PortalMat::operator=(MatExpr&) this=%p datastart=%p\n", this, datastart);
}

PortalMat& PortalMat::operator = (const cv::Mat& o)
{
    *(cv::Mat*)this = o;
    fprintf(stderr, "PortalMat::operator=(Mat&) this=%p datastart=%p\n", this, datastart);
}

int PortalMat::reference()
{
    int ref = 0;
    //fprintf(stderr, "PortalMat::reference this=%p datastart=%p\n", this, datastart);
    ref = matAllocator->reference(refcount, datastart, data);
    return ref;
}

bool PortalMat::copy(cv::Mat &other)
{
    create(other.rows, other.cols, CV_32F);
    for (int i = 0; i < rows; i++) {
	for (int j = 0; j < cols; j++) {
	    at<float>(i, j) = other.at<float>(i, j);
	}
    }
    return true;
}

bool PortalMat::copy(cv::MatExpr other)
{
    cv::Mat m(other);
    create(m.rows, m.cols, CV_32F);
    for (int i = 0; i < rows; i++) {
	for (int j = 0; j < cols; j++) {
	    at<float>(i, j) = m.at<float>(i, j);
	}
    }
    return true;
}

bool PortalMat::transpose(cv::Mat &other)
{
    create(other.cols, other.rows, CV_32F);
    for (int i = 0; i < rows; i++) {
	for (int j = 0; j < cols; j++) {
	    at<float>(i, j) = other.at<float>(j, i);
	}
    }
    return true;
}

bool PortalMat::compare(Mat &other, const char *file, int line, float epsilon, Mat *pm, bool verbose)
{
    if (0)
	fprintf(stderr, "PortalMat.compare rows=%d cols=%d other.rows=%d other.cols=%d\n",
		rows, cols, other.rows, other.cols);

    if (rows != other.rows || cols != other.cols) {
	fprintf(stderr, "PortalMat.compare dimension mismatch rows=%d cols=%d other.rows=%d other.cols=%d\n",
		rows, cols, other.rows, other.cols);
	return false;
    }
    bool rv = true;
    for (int i = 0; i < rows; i++) {
	for (int j = 0; j < cols; j++) {
	    float v = at<float>(i, j);
	    float ov = other.at<float>(i, j);
	    if (fabs((v - ov)/ov) > epsilon) {
		if (file)
		  if(verbose) fprintf(stderr, "%s:%d: ", file, line);
		if(verbose) fprintf(stderr, "mismatch[%d,%d] expected %f got %f error=%f", i, j, v, ov, fabs(v - ov));
		if (pm) {
		    float pmv = pm->at<float>(i,j);
		    if(verbose) fprintf(stderr, " pm[%d,%d]=%f %08x", i, j, pmv, *(int*)&pmv);
		}
		if(verbose) fprintf(stderr, "\n");
		rv = false;
	    }
	}
    }
    return rv;
}


void PortalMat::naive_mul(cv::Mat &a, cv::Mat &b, FILE *f)
{

  fprintf(stderr, "a:(%d x %d) b:(%d x %d)", a.rows, a.cols, b.rows, b.cols);
  assert(a.cols == b.rows);
  create(a.rows, b.cols, CV_32F);
  for (int i = 0; i < rows; i++) {
    for (int j = 0; j < cols; j++) {
      double c = 0.0;
#ifndef __FOO
      bool last = (i==(rows-1) && j==(cols-1));
      if(last) fprintf(f, "c = 0.0;\n");
      for(int l = 0; l < a.cols; l++) {
	double x = (double)a.at<float>(i,l);
	double y = (double)b.at<float>(l,j);
	double p = x*y;
	if(last){
	  fprintf(f, "assert(c==%f);\n", c);
	}
      	c = c + p;
	if(last){
	  fprintf(f, "p = %f*%f;\n", x, y);
	  fprintf(f, "assert(p==%f);\n", p);
	  fprintf(f, "c = c + p;\n");
	  fprintf(f, "disp([c, %f])\n", c);
	  fprintf(f, "assert(c==%f)\n", c);
	}
      }
      at<float>(i, j) = (float)c;
      if (last) fprintf(f, "rez = %f;\n", c);
#else
      int K = 2;
      int gatherSz = 8/K;
      float c_ij[gatherSz];
      for(int k = 0; k < gatherSz; k++)
	c_ij[k] = 0.0;
      for(int l = 0; l < a.cols; l+=gatherSz)
	for(int k = 0; k < gatherSz; k++)
	  c_ij[k] += a.at<float>(i,l+k) * b.at<float>(l+k,j);
      for(int k = 0; k < gatherSz; k++)
	c += c_ij[k];
      at<float>(i, j) = c;
#endif
    }
  }
}


#ifdef MATRIX_NT

/*!
 * Multiplies a * b-transpose
 */
void PortalMat::multf(PortalMat &a, PortalMat &b_transpose,  MmIndication *mmind)
{
    if (a.cols != b_transpose.cols) {
	fprintf(stderr, "Mismatched matrices: a.rows=%d a.cols=%d b.rows=%d b.cols=%d\n", a.rows, a.cols, b_transpose.rows, b_transpose.cols);
	return;
    }
    long aref = a.reference();
    long bref = b_transpose.reference();
    long cref = reference();
    if (0)
    fprintf(stderr, "mult: ref=%d rows=%d cols=%d a.ref=%d a.rows=%d a.cols=%d b.ref=%d b.rows=%d b.cols=%d\n",
	    cref, rows, cols,
	    aref, a.rows, a.cols,
	    bref, b_transpose.rows, b_transpose.cols);
    mmdevice->mmf(aref, a.rows, a.cols,
		  bref, b_transpose.rows, b_transpose.cols,
		  cref,
		  a.rows*a.cols, a.cols*J_VALUE,
		  b_transpose.rows*b_transpose.cols, b_transpose.cols*K_VALUE,
		  a.rows*b_transpose.rows, b_transpose.rows*J_VALUE);

    sem_wait(&mul_sem);
    if(mmind) {
      int macs = a.rows*a.cols*b_transpose.rows;
      if (0)
	fprintf(stderr, "macs %d cycles %f lap_timer %f macs/cycle: %f\n", macs, (float)mmind->ccnt, (float)portalTimerLap(0), ((float)macs)/((float)mmind->ccnt));
    }
}


#else
#ifdef MATRIX_TN
/*!
 * Multiplies a * b
 */
void PortalMat::multf(PortalMat &a, PortalMat &b,  MmIndication *mmind)
{
    if (a.rows != b.rows) {
	fprintf(stderr, "Mismatched matrices: a.rows=%d a.cols=%d b.rows=%d b.cols=%d\n", a.rows, a.cols, b.rows, b.cols);
	return;
    }
    long aref = a.reference();
    long bref = b.reference();
    long cref = reference();
    if (0)
    fprintf(stderr, "mult: ref=%ld rows=%d cols=%d a.ref=%ld a.rows=%d a.cols=%d b.ref=%ld b.rows=%d b.cols=%d\n",
	    cref, rows, cols,
	    aref, a.rows, a.cols,
	    bref, b.rows, b.cols);
    mmdevice->mmf(aref, a.rows, a.cols,
		  bref, b.rows, b.cols,
		  cref,
		  a.rows*a.cols, a.cols*J_VALUE,
		  a.rows*b.cols, b.cols*J_VALUE,
		  a.cols*b.cols, b.rows*b.cols);

    sem_wait(&mul_sem);
    if(mmind) {
      int macs = a.rows*a.cols*b.rows;
      if (0)
	fprintf(stderr, "macs %d cycles %f lap_timer %f macs/cycle: %f\n", macs, (float)mmind->ccnt, (float)portalTimerLap(0), ((float)macs)/((float)mmind->ccnt));
    }
}

#endif
#endif


template<typename T>
void dumpMatF(const char *prefix, const char *fmt, const cv::Mat &mat, FILE *ofile)
{
  fprintf(ofile, "%s: rows=%d cols=%d mat=%p\n", prefix, mat.rows, mat.cols, &mat);
  for (int i = 0; i < mat.rows; i++) {
    fprintf(ofile, "%s: %03d:", prefix, i);
    for (int j = 0; j < mat.cols; j++) {
      fprintf(ofile, " ");
      fprintf(ofile, fmt, mat.at<T>(i, j));
    }
    fprintf(ofile, "\n");
  }
}
template void dumpMatF<float>(const char *prefix, const char *fmt, const cv::Mat &mat, FILE *ofile);

template<typename T>
void dumpMatOctave(const char *name, const char *fmt, const cv::Mat &mat, FILE *ofile)
{
  fprintf(ofile, "%s=[", name);
  for (int i = 0; i < mat.rows; i++) {
    for (int j = 0; j < mat.cols; j++) {
      fprintf(ofile, " ");
      fprintf(ofile, fmt, mat.at<T>(i, j));
      if(j+1 < mat.cols)
	fprintf(ofile, ",");
    }
    if(i+1 < mat.rows)
      fprintf(ofile, ";");
  }
  fprintf(ofile,"];\n");
}
template void dumpMatOctave<float>(const char *name, const char *fmt, const cv::Mat &mat, FILE *ofile);

template<typename T>
void dumpMat(const char *prefix, const char *fmt, const cv::Mat &mat)
{
  dumpMatF<T>(prefix,fmt,mat,stderr);
}
template void dumpMat<float>(const char *prefix, const char *fmt, const cv::Mat &mat);
template void dumpMat<int>(const char *prefix, const char *fmt, const cv::Mat &mat);
