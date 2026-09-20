#include "bme68x_stm32.h"

// Connects to the primary I2C bus initialized in main.c
extern I2C_HandleTypeDef hi2c1;

// I2C Read Wrapper
int8_t bme68x_i2c_read(uint8_t reg_addr, uint8_t *reg_data, uint32_t len, void *intf_ptr) {
    uint8_t dev_addr = *(uint8_t*)intf_ptr;

    if (HAL_I2C_Mem_Read(&hi2c1, dev_addr << 1, reg_addr, 1, reg_data, len, 100) == HAL_OK) {
        return 0; // BME68X_OK
    }
    return -1; // BME68X_E_COM_FAIL
}

// I2C Write Wrapper
int8_t bme68x_i2c_write(uint8_t reg_addr, const uint8_t *reg_data, uint32_t len, void *intf_ptr) {
    uint8_t dev_addr = *(uint8_t*)intf_ptr;

    if (HAL_I2C_Mem_Write(&hi2c1, dev_addr << 1, reg_addr, 1, (uint8_t*)reg_data, len, 100) == HAL_OK) {
        return 0; // BME68X_OK
    }
    return -1; // BME68X_E_COM_FAIL
}

// Microsecond Delay Wrapper
void bme68x_delay_us(uint32_t period, void *intf_ptr) {
    HAL_Delay((period / 1000) + 1);
}
