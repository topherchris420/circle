# ESP32-S3 Pin Allocation

> **ENGINEERING REVIEW ONLY ? NOT FOR FABRICATION OR HUMAN CONNECTION.**

| GPIO | Function | Direction | Boot state | Strapping risk | Pull | Timing role | Sheet |
|---|---|---|---|---|---|---|---|
| GPIO0 | BOOT_BUTTON_ONLY | Bidirectional/Output | High-Z | YES | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO1 | SYNC_IN_CAPTURE | Input | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO2 | SYNC_OUT_DRIVE | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO3 | RESERVED_STRAP | Bidirectional/Output | High-Z | YES | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO4 | SD_CLK | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO5 | SD_CMD | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO6 | SD_D0 | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO7 | SD_D1 | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO8 | SYS_I2C_SDA | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO9 | SYS_I2C_SCL | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO10 | IMU_SCLK | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO11 | IMU_MOSI | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO12 | IMU_MISO | Input | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO13 | IMU_CS_N | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO14 | IMU_DRDY | Input | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO15 | SD_D2 | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO16 | SD_D3 | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO17 | PPG_SDA_3V3 | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO18 | PPG_SCL_3V3 | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO19 | USB_D_MINUS | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO20 | USB_D_PLUS | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO21 | PPG_INT_N_WIRED_OR | Input | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO35 | UNAVAILABLE_OCTAL_PSRAM | Bidirectional/Output | High-Z | PSRAM | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO36 | UNAVAILABLE_OCTAL_PSRAM | Bidirectional/Output | High-Z | PSRAM | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO37 | UNAVAILABLE_OCTAL_PSRAM | Bidirectional/Output | High-Z | PSRAM | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO38 | ISO_HEALTH_CHALLENGE | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO39 | EDA_SCLK | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO40 | EDA_MOSI | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO41 | EDA_MISO | Input | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO42 | EDA_CS_N | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO43 | DEBUG_UART_TX | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO44 | DEBUG_UART_RX | Bidirectional/Output | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO45 | EDA_FW_REQUEST | Bidirectional/Output | LOW required | YES | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO46 | HAPTIC_CURRENT_EDGE | Input | LOW required | YES | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO47 | EDA_DRDY | Input | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
| GPIO48 | SYS_STATUS_INT_N | Input | High-Z | No | Design-specific | Interrupt/DMA where named | 01_compute_usb |
