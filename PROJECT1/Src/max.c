#include "max30102.h"

void MAX30102_Init(I2C_HandleTypeDef *hi2c) {
    uint8_t data;

    // Reset the sensor (Register 0x09)
    data = 0x40;
    HAL_I2C_Mem_Write(hi2c, MAX30102_ADDR, 0x09, 1, &data, 1, 100);
    HAL_Delay(100);

    // Set SpO2 Mode (Register 0x09)
    data = 0x03;
    HAL_I2C_Mem_Write(hi2c, MAX30102_ADDR, 0x09, 1, &data, 1, 100);

    // Set LED Pulse Amplitude (Registers 0x0C and 0x0D)
    data = 0x24; // ~7mA for IR and Red LEDs
    HAL_I2C_Mem_Write(hi2c, MAX30102_ADDR, 0x0C, 1, &data, 1, 100);
    HAL_I2C_Mem_Write(hi2c, MAX30102_ADDR, 0x0D, 1, &data, 1, 100);
}

void MAX30102_Read(I2C_HandleTypeDef *hi2c, uint32_t *ir_data, uint32_t *red_data) {
    uint8_t buffer[6];

    // Read 6 bytes from the FIFO Data Register (0x07)
    HAL_I2C_Mem_Read(hi2c, MAX30102_ADDR, 0x07, 1, buffer, 6, 100);

    // Reconstruct the 18-bit values from the 3-byte chunks
    *red_data = ((buffer[0] << 16) | (buffer[1] << 8) | buffer[2]) & 0x03FFFF;
    *ir_data = ((buffer[3] << 16) | (buffer[4] << 8) | buffer[5]) & 0x03FFFF;
}
