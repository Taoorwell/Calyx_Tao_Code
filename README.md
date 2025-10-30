# 🧭 Tao's Python Tools Overview & Applications

Tao has implemented a **full suite of tools and workflows** in a Python notebook, providing analysis and data processing for various project types (**REDD**, **ARR**, **IFM**, etc.).  
The notebook currently supports the following **analytical modules and tools**.

---

## 🛠️ Tool Summaries

### 1. Deforestation Extraction (TMF & GFW Layers)

**Inputs:**
- Project shapefile (e.g., protected area polygon)

**Outputs:**
- Tabular summaries of **Global Forest Watch (GFW)** and **Tropical Moist Forest (TMF)** deforestation data

**Functionality:**
- Automatically generates buffers around the project area to extract nearby deforestation signals  
- Currently used only for **REDD projects**, but recommended to expand to **all project types**

---

### 2. ACR Inherent Risk Analysis Tool

**Inputs:**
- Project shapefile  
- Project year  

**Outputs:**
- Tree height distributions (10 m resolution dataset)  
- Slope of the project area  
- Protected areas within the project area  
- Distance from streams  
- Biomass distribution (cumulative)  
- ESA Land Cover  
- Global Forest Watch historical tree loss  

**Purpose:**
- Supports the **ACR inherent risk rating** process by evaluating above-ground biomass potential and historical loss  
- Enhances **baseline accuracy** and helps tailor **project-specific risk assessments**

---

### 3. CAR Mexico Biomass Change (2010–2021)

**Focus:**  
Analysis of biomass change using **ESA datasets** between 2010 – 2021

**Spatial Scope:**  
Applies to both the **Project Area (PA)** and **Adjacent Area (AA)**

**Action Item:**  
Add output functionality for **GeoTIFF export** for easier map production and visualization

---

### 4. Grasslands Monitoring Tool

**Inputs:**  
- Project shapefile  

**Outputs:**  
- Seasonal vegetation indices:
  - **NDVI** (Normalized Difference Vegetation Index)  
  - Three other **Landsat-based indices**

**Notes:**
- You can input any vegetation index, but must modify the code and year parameters

**Goal:**  
Assess seasonal trends in **grassland conditions** to support the **AA Baseline** and **PA Additionality** assessments and monitoring

---

### 5. Blue Carbon Module

**Key Layers & Metrics:**
- **Global Mangrove Watch (GMW)**
- **NDVI** for vegetation productivity  
- **Water & mangrove dynamics:**
  - Water gain & mangrove gain  
  - Water gain & mangrove loss  
  - Water loss & mangrove gain  
  - Water loss & mangrove loss  

**Use Case:**  
Supports projects in **mangrove and coastal wetland ecosystems** to quantify **carbon sequestration** and **hydrological changes**

---

### 6. LUCA Automation Tools

**Version 1:**  
- Designed for **single-project** runs  

**Version 2:**  
- Supports **batch processing** of multiple projects  

**Limitations:**  
- Cannot currently aggregate outputs at the **year level**  
- **Disturbance analysis** since the latest Validation Report (VR) must be performed manually

---

## 📘 Summary
Tao’s notebook provides a **comprehensive analytical framework** supporting diverse project types and data sources.  
Each tool aims to **streamline workflows**, improve **baseline and monitoring accuracy**, and **enhance automation** across projects.


## 🚀 Quick Start

Follow these steps to get started with Tao’s Python tools:

```bash
# 1. Clone the repository
git clone https://github.com/USERNAME/REPO.git
cd REPO

# 2. Create and activate the conda environment
conda env create -f environment_geemap.yml
conda activate geemap

# 2-1. For LUCA tool you may need a new envrionment
conda env create -f environment_selen.yml
conda activate selen

# 3. Launch Jupyter Notebook
jupyter notebook


