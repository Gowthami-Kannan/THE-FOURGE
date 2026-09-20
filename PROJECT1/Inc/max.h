#ifndef INC_MAX30102_H_
#define INC_MAX30102_H_

#include "stm32f4xx_hal.h"

// MAX30102 I2C Address (0xAE for Write, 0xAF for Read)
#define MAX30102_ADDR 0xAE

void MAX30102_Init(I2C_HandleTypeDef *hi2c);
void MAX30102_Read(I2C_HandleTypeDef *hi2c, uint32_t *ir_buffer, uint32_t *red_buffer);

#endif /* INC_MAX30102_H_ */
