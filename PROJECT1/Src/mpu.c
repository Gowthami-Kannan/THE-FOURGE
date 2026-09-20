#include "mpu6050.h"

// Initialize the accelerometer
void MPU6050_Init(I2C_HandleTypeDef *hi2c) {
    uint8_t check;
    uint8_t Data;

    // Check if the sensor is responding
    HAL_I2C_Mem_Read(hi2c, MPU6050_ADDR, 0x75, 1, &check, 1, 1000);

    if (check == 104) { // 104 is the default WHO_AM_I response for MPU6050
        // Wake up the sensor (Power Management 1 Register)
        Data = 0;
        HAL_I2C_Mem_Write(hi2c, MPU6050_ADDR, 0x6B, 1, &Data, 1, 1000);

        // Set Accelerometer configuration (+- 2g)
        Data = 0x00;
        HAL_I2C_Mem_Write(hi2c, MPU6050_ADDR, 0x1C, 1, &Data, 1, 1000);
    }
}

// Read the XYZ data
void MPU6050_Read_All(I2C_HandleTypeDef *hi2c, MPU6050_t *DataStruct) {
    uint8_t Rec_Data[6];

    // Read 6 bytes of data starting from register 0x3B (ACCEL_XOUT_H)
    HAL_I2C_Mem_Read(hi2c, MPU6050_ADDR, 0x3B, 1, Rec_Data, 6, 1000);

    DataStruct->Accel_X_RAW = (int16_t)(Rec_Data[0] << 8 | Rec_Data[1]);
    DataStruct->Accel_Y_RAW = (int16_t)(Rec_Data[2] << 8 | Rec_Data[3]);
    DataStruct->Accel_Z_RAW = (int16_t)(Rec_Data[4] << 8 | Rec_Data[5]);

    // Convert raw data to standard gravitational units (g)
    DataStruct->Ax = DataStruct->Accel_X_RAW / 16384.0;
    DataStruct->Ay = DataStruct->Accel_Y_RAW / 16384.0;
    DataStruct->Az = DataStruct->Accel_Z_RAW / 16384.0;
}
