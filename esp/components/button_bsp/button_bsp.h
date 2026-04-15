#ifndef BUTTON_BSP_H
#define BUTTON_BSP_H
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
extern EventGroupHandle_t key_groups;

void button_Init(void);

void GPIO_SET(uint8_t pin,uint8_t mode);
uint8_t GPIO_GET(uint8_t pin);

#endif