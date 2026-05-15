# Trip & TAT Analytics Suite

A production-ready Streamlit application for logistics performance analytics, providing comprehensive trip analysis and turnaround time (TAT) monitoring.

## Features

### Trip Report Analysis
- **Trip Metrics**: Total trips, loaded/empty ratio, quantity analysis
- **Destination Analysis**: Trip distribution by destination with quantity tracking
- **Plant Analysis**: Performance comparison across different plants
- **Monthly Trends**: Volume trends over time with cumulative tracking
- **Anomaly Detection**: Automatic identification of data anomalies (zero quantity, outliers)

### TAT Report Analysis
- **Stage Breakdown**: Detailed analysis of each TAT stage (DO receipt to unloading)
- **SLA Compliance**: Track performance against defined thresholds
- **Bottleneck Detection**: Identify stages causing delays
- **Percentile Analysis**: Distribution statistics for better insights
- **Plant/Client Comparison**: Comparative analysis across dimensions

### Data Processing
- **Advanced Deduplication**: Intelligent merging of duplicate Trip Nos with configurable aggregation (sum for quantities, average for TAT stages)
- **Fuzzy Destination Matching**: Automatic standardization of destination names
- **Data Validation**: Schema validation with meaningful error messages
- **Audit Trail**: Complete log of all deduplication operations

## Installation

### Prerequisites
- Python 3.9 or higher
- pip package manager

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd trip_tat_analytics
