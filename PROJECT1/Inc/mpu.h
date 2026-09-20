#ifndef INC_MPU6050_H_
#define INC_MPU6050_H_

// Directly include the F4 series hardware libraries to prevent compiler errors
#include "stm32f4xx_hal.h"

#define MPU6050_ADDR 0xD0

// Data Structure to hold X, Y, Z values
typedef struct {
    float Accel_X_RAW;
    float Accel_Y_RAW;
    float Accel_Z_RAW;
    float Ax;
    float Ay;
    float Az;
} MPU6050_t;

// Function Prototypes
void MPU6050_Init(I2C_HandleTypeDef *hi2c);
void MPU6050_Read_All(I2C_HandleTypeDef *hi2c, MPU6050_t *DataStruct);

#endif /* INC_MPU6050_H_ */
