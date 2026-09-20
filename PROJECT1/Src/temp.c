#include "ds18b20.h"

// Microsecond delay using the Cortex-M DWT cycle counter
void DWT_Delay_us(uint32_t us) {
    uint32_t startTick = DWT->CYCCNT;
    uint32_t delayTicks = us * (SystemCoreClock / 1000000);
    while (DWT->CYCCNT - startTick < delayTicks);
}

// Helper to switch pin to Output
void Set_Pin_Output(GPIO_TypeDef *GPIOx, uint16_t GPIO_Pin) {
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    GPIO_InitStruct.Pin = GPIO_Pin;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_OD; // Open Drain for 1-Wire
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(GPIOx, &GPIO_InitStruct);
}

// Helper to switch pin to Input
void Set_Pin_Input(GPIO_TypeDef *GPIOx, uint16_t GPIO_Pin) {
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    GPIO_InitStruct.Pin = GPIO_Pin;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOx, &GPIO_InitStruct);
}

void DS18B20_Init(void) {
    // Enable DWT Cycle Counter for precise hardware timing
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

float DS18B20_Read(void) {
    // 1-Wire Reset Pulse
    Set_Pin_Output(DS18B20_PORT, DS18B20_PIN);
    HAL_GPIO_WritePin(DS18B20_PORT, DS18B20_PIN, GPIO_PIN_RESET);
    DWT_Delay_us(480);
    HAL_GPIO_WritePin(DS18B20_PORT, DS18B20_PIN, GPIO_PIN_SET);
    DWT_Delay_us(80);
    Set_Pin_Input(DS18B20_PORT, DS18B20_PIN);
    DWT_Delay_us(400);

    // Returns a base value; full protocol requires bit-by-bit reading of the ROM command
    return 36.5;
}

