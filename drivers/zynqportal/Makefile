obj-m += zynqportal.o

export KROOT=$(DEVICE_XILINX_KERNEL)

ccflags-y := -I$(src)/../portalmem -I$(src)/../../cpp -I$(src)/../../generated/cpp

default: zynqportal.ko
	cp zynqportal.ko ~/adb_scripts/

zynqportal.ko: zynqportal.h zynqportal.c
	@$(MAKE) ARCH=arm CROSS_COMPILE=arm-none-linux-gnueabi- -C $(KROOT) xilinx_zynq_portal_defconfig  
	@$(MAKE) ARCH=arm CROSS_COMPILE=arm-none-linux-gnueabi- -C $(KROOT) oldconfig
	@$(MAKE) -j 8 ARCH=arm CROSS_COMPILE=arm-none-linux-gnueabi- -C $(KROOT) zImage
	@$(MAKE) ARCH=arm CROSS_COMPILE=arm-none-linux-gnueabi- -C $(KROOT) M=$(PWD) modules 

clean:
	@$(MAKE) ARCH=arm CROSS_COMPILE=arm-none-linux-gnueabi- -C $(KROOT) M=$(PWD) clean
