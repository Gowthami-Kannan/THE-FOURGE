#ifndef INC_DS18B20_H_
#define INC_DS18B20_H_

#include "stm32f4xx_hal.h"

// Define the GPIO Port and Pin configured in your .ioc file (Default PA4 used here)
#define DS18B20_PORT GPIOA
#define DS18B20_PIN  GPIO_PIN_4

void DS18B20_Init(void);
float DS18B20_Read(void);
void DWT_Delay_us(uint32_t us);

#endif /* INC_DS18B20_H_ */
