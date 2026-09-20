################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (13.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Src/air.c \
../Src/main.c \
../Src/max.c \
../Src/mpu.c \
../Src/syscalls.c \
../Src/sysmem.c \
../Src/temp.c 

OBJS += \
./Src/air.o \
./Src/main.o \
./Src/max.o \
./Src/mpu.o \
./Src/syscalls.o \
./Src/sysmem.o \
./Src/temp.o 

C_DEPS += \
./Src/air.d \
./Src/main.d \
./Src/max.d \
./Src/mpu.d \
./Src/syscalls.d \
./Src/sysmem.d \
./Src/temp.d 


# Each subdirectory must supply rules for building sources it contributes
Src/%.o Src/%.su Src/%.cyclo: ../Src/%.c Src/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DDEBUG -DSTM32 -DSTM32G474CCUx -DSTM32G4 -c -I"C:/Users/gowthamikannan/Downloads/reqd_files/reqd_files/CMSIS/Device/ST/STM32F4xx/Include" -I"C:/Users/gowthamikannan/Downloads/reqd_files/reqd_files/CMSIS/DSP/Include" -I"C:/Users/gowthamikannan/Downloads/reqd_files/reqd_files/CMSIS/Core/Include" -I"C:/Users/gowthamikannan/Downloads/reqd_files/reqd_files/CMSIS/Include" -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Src

clean-Src:
	-$(RM) ./Src/air.cyclo ./Src/air.d ./Src/air.o ./Src/air.su ./Src/main.cyclo ./Src/main.d ./Src/main.o ./Src/main.su ./Src/max.cyclo ./Src/max.d ./Src/max.o ./Src/max.su ./Src/mpu.cyclo ./Src/mpu.d ./Src/mpu.o ./Src/mpu.su ./Src/syscalls.cyclo ./Src/syscalls.d ./Src/syscalls.o ./Src/syscalls.su ./Src/sysmem.cyclo ./Src/sysmem.d ./Src/sysmem.o ./Src/sysmem.su ./Src/temp.cyclo ./Src/temp.d ./Src/temp.o ./Src/temp.su

.PHONY: clean-Src

