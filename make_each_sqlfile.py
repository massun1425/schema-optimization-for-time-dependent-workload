import os

def save_sql_files(input_folder, output_folder):
	# Ensure the output folder exists
	os.makedirs(output_folder, exist_ok=True)
	num = 0
	# Iterate through all files in the input folder
	for path, subdirs, files in os.walk(input_folder):
		for name in files:
			input_file = os.path.join(path, name)
			output_file = os.path.join(output_folder, name)
			if input_file.endswith(".sql"):
				# copies files into output folder
				with open(input_file, 'r') as sql_file:
					data = sql_file.read()
					sql_file.close()
				with open(output_file, "w+") as out:
					out.write(data)
				num+=1
	print(num)

if __name__ == "__main__":
	# Input folder containing % folders with .sql files
	input_folder = "dataset/redbench/imdb/benchmarks"
	# Output folder to save queries
	output_folder = "dataset/RED_SQL"

	save_sql_files(input_folder, output_folder)