#ifndef INC_BME68X_STM32_H_
#define INC_BME68X_STM32_H_

#include "stm32f4xx_hal.h"

// Define the API function signatures expected by Bosch
int8_t bme68x_i2c_read(uint8_t reg_addr, uint8_t *reg_data, uint32_t len, void *intf_ptr);
int8_t bme68x_i2c_write(uint8_t reg_addr, const uint8_t *reg_data, uint32_t len, void *intf_ptr);
void bme68x_delay_us(uint32_t period, void *intf_ptr);

#endif /* INC_BME68X_STM32_H_ */
