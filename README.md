# STS-backend

# TODOS

## Create route OR GraphQL query to do the following

### Dataset page queries

1. GET all clinical and preclinical datasets from the MySQL database (return in json)
    - The query should simply recieve a parameter that can other be "clinical" OR "preclinical" and will return ALL fields associated with the dataset from the DB (including it's ID).
	- OUTPUT FORMAT:
	```JSON
		{
			id: 0,
			name: "",
			version: "",
			description: "",
			layers: ""
		}
	```

2. Given a Dataset ID and the clinical/preclinical indication as parameters, GET the following (return in json)
	- Associated numerical total of samples/cell lines (along with the following distributions totals: age (0-18/19-25/26-50/51-65/66-75/75+)/race (list of different racial types)/ethnicity (list of different ethnicity types)/cancer types (list of different cancer types)), drugs (list of different drugs along with MOA if available [could be retrieved from annotationdb on the fly]), total number of genes.
	- OUTPUT FORMAT:
	```JSON
		{
			total: 0,
			ageDistribution: {
				"0-18": 0,
				"19-25": 0,
				"26-50": 0,
				"51-65": 0,
				"66-75": 0,
				"75+": 0
			},
			racialDistribution: {
				"White": 0,
				"Black": 0,
				"Asian": 0,
				"Other": 0
			},
			ethnicityDistribution: {
				"Hispanic": 0,
				"Non-Hispanic": 0,
				"Other": 0
			},
			cancerTypesDistribution: {
				"Rhabdomyosarcoma": 0,
				"Synovial Sarcoma": 0,
				"Liposarcoma": 0,
				"Other": 0
			},
			tissueDistribution: {
				"soft-tissue": 0,
				"uterine": 0,
				"other": 0
			},
			drugs: ["Drug1", "Drug2", "Drug3"],
			genes: 0
		}
	```

### Visualization page

1. GET all clinical and preclinical datasets from the MySQL database (return in json) [same query as the Dataset page]
    - The query should simply recieve a parameter that can other be "clinical" OR "preclinical" and will return ALL fields associated with the dataset from the DB (including it's ID).
	- OUTPUT FORMAT:
	```JSON
		{
			id: 0,
			name: "",
			version: "",
			description: "",
			layers: ""
		}
	```

2. Given datasetID,the clinical/preclinical indication, and the data layer, return the following (return in json):
	- All gene names along with identifiers for the data layer in question (decide what would be best based on stored fields)
	- OUTPUT FORMAT:
	```JSON
		{
			genes: [
				{
					id: 0,
					name: ""
				},
				{
					id: 0,
					name: ""
				}
			]
		}
	```

3. Given a Dataset ID, the clinical/preclinical indication, data layer (RNAseq, Mutations, etc), and one or more gene identifier (decide what would be best based on stored fields) fields as parameters, GET the following (return in json)
	- Sample/cell line, tissue (soft tissue, uterine, etc [can be retrieved from annotationDB on the fly]), along with the associated gene)
	- OUTPUT FORMAT:
	```json
		{
			ATRX: [
			{ cellLine: 'Rh41', value: 7.1, tissue: 'Soft Tissue' },
			{ cellLine: 'Hs 729.T', value: 7.24, tissue: 'Soft Tissue' },
			{ cellLine: 'GCT', value: 7.73, tissue: 'Soft Tissue' },
			{ cellLine: 'Rh30', value: 7.93, tissue: 'Soft Tissue' },
			{ cellLine: 'HT-1080', value: 7.97, tissue: 'Soft Tissue' },
			{ cellLine: 'MES-SA', value: 8.16, tissue: 'Uterus' },
			{ cellLine: 'RKN', value: 8.22, tissue: 'Soft Tissue' },
			{ cellLine: 'RD', value: 8.26, tissue: 'Soft Tissue' },
			{ cellLine: 'TE 159.T', value: 8.3, tissue: 'Soft Tissue' },
			{ cellLine: 'TE 125.T', value: 8.33, tissue: 'Soft Tissue' },
			{ cellLine: 'Rh18', value: 8.34, tissue: 'Soft Tissue' },
			{ cellLine: 'TE 441.T', value: 8.49, tissue: 'Soft Tissue' },
			{ cellLine: 'TE 617.T', value: 8.54, tissue: 'Soft Tissue' },
			{ cellLine: 'ESS-1', value: 8.65, tissue: 'Uterus' },
			{ cellLine: 'A-204', value: 8.7, tissue: 'Soft Tissue' },
			{ cellLine: 'KYM-1', value: 8.96, tissue: 'Soft Tissue' },
			{ cellLine: 'SK-UT-1', value: 9.08, tissue: 'Uterus' },
			{ cellLine: 'SK-LMS-1', value: 9.18, tissue: 'Soft Tissue' }
		],
		TP53: [
			{ cellLine: 'Rh41', value: 5.8, tissue: 'Soft Tissue' },
			{ cellLine: 'Hs 729.T', value: 6.12, tissue: 'Soft Tissue' },
			{ cellLine: 'GCT', value: 6.44, tissue: 'Soft Tissue' },
			{ cellLine: 'Rh30', value: 6.5, tissue: 'Soft Tissue' },
			{ cellLine: 'HT-1080', value: 6.73, tissue: 'Soft Tissue' },
			{ cellLine: 'MES-SA', value: 7.0, tissue: 'Uterus' },
			{ cellLine: 'RKN', value: 7.15, tissue: 'Soft Tissue' },
			{ cellLine: 'RD', value: 7.22, tissue: 'Soft Tissue' },
			{ cellLine: 'TE 159.T', value: 7.35, tissue: 'Soft Tissue' },
			{ cellLine: 'TE 125.T', value: 7.41, tissue: 'Soft Tissue' },
			{ cellLine: 'Rh18', value: 7.48, tissue: 'Soft Tissue' },
			{ cellLine: 'TE 441.T', value: 7.66, tissue: 'Soft Tissue' },
			{ cellLine: 'TE 617.T', value: 7.78, tissue: 'Soft Tissue' },
			{ cellLine: 'ESS-1', value: 7.9, tissue: 'Uterus' },
			{ cellLine: 'A-204', value: 8.05, tissue: 'Soft Tissue' },
			{ cellLine: 'KYM-1', value: 8.22, tissue: 'Soft Tissue' },
			{ cellLine: 'SK-UT-1', value: 8.4, tissue: 'Uterus' },
			{ cellLine: 'SK-LMS-1', value: 8.55, tissue: 'Soft Tissue' }
		],
		RB1: [
			{ cellLine: 'Rh41', value: 6.3, tissue: 'Soft Tissue' },
			{ cellLine: 'Hs 729.T', value: 6.55, tissue: 'Soft Tissue' },
			{ cellLine: 'GCT', value: 6.78, tissue: 'Soft Tissue' },
			{ cellLine: 'Rh30', value: 6.91, tissue: 'Soft Tissue' },
			{ cellLine: 'HT-1080', value: 7.02, tissue: 'Soft Tissue' },
			{ cellLine: 'MES-SA', value: 7.18, tissue: 'Uterus' },
			{ cellLine: 'RKN', value: 7.31, tissue: 'Soft Tissue' },
			{ cellLine: 'RD', value: 7.45, tissue: 'Soft Tissue' },
			{ cellLine: 'TE 159.T', value: 7.53, tissue: 'Soft Tissue' },
			{ cellLine: 'TE 125.T', value: 7.6, tissue: 'Soft Tissue' },
			{ cellLine: 'Rh18', value: 7.72, tissue: 'Soft Tissue' },
			{ cellLine: 'TE 441.T', value: 7.88, tissue: 'Soft Tissue' },
			{ cellLine: 'TE 617.T', value: 7.94, tissue: 'Soft Tissue' },
			{ cellLine: 'ESS-1', value: 8.1, tissue: 'Uterus' },
			{ cellLine: 'A-204', value: 8.25, tissue: 'Soft Tissue' },
			{ cellLine: 'KYM-1', value: 8.38, tissue: 'Soft Tissue' },
			{ cellLine: 'SK-UT-1', value: 8.52, tissue: 'Uterus' },
			{ cellLine: 'SK-LMS-1', value: 8.7, tissue: 'Soft Tissue' }
		]
	}
	```

    
    