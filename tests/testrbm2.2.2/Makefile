
BSCFLAGS=-aggressive-conditions -show-schedule -keep-fires -p +:../paclib

XBSVDIR=../..
MMDIR=../../examples/matmul
RBMDIR=../../examples/rbm
DBNTOPBSV= $(RBMDIR)/Top.bsv
TESTCPPFILES= $(RBMDIR)/testrbm.cpp
XBSVFLAGS = -D J_VALUE=2 -D K_VALUE=2 -D N_VALUE=2 -D DataBusWidth=64

include $(MMDIR)/Makefile.mm
include $(RBMDIR)/Makefile.rbm
include $(XBSVDIR)/Makefile.common

