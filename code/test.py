import os
import pandas as pd
import numpy as np
import csv
import tensorflow as tf
import re
import sys

import keras
import keras.backend as k
from keras.models import load_model

from sklearn.metrics import confusion_matrix

from train import configureKerasForGPU, argparse, atoi, natural_keys

from pickle import load

def defineArgParsers():

	parser = argparse.ArgumentParser(description='Test model.')

	# MANDATORY
	required = parser.add_argument_group('required arguments')
	required.add_argument("--campaingPath", type=str, default='', help="Path where the campaing data is located. Type -> string. Example -> --campaingPath='tables\\radar\\rice_A,B_DESC,ASC_2016-09-01_2017-08-31'")
	required.add_argument("--tags_name", type=str, default='', help="Tag filename of the regions. Only requerided when 'networkPath' is empty. Type -> string. Example -> --tags_name='tags.csv'")
	required.add_argument("--nameExperiment", type=str, default='', help="Experiment name (activity,rice). Only requerided when 'networkPath' is empty. Type -> string. Example -> --nameExperiment='activity'")

	# OPTIONAL
	parser.add_argument("--networkPath", type=str, default='', help="Path where the model is located. Type -> string. Example -> --networkPath='experiments\\rice\\models\rice_A_ASC-cF_True\\LSTM-lr1.0e-03-bs16-drop0.20-hnes[128]-hne[64]-epo100-seqLen108-cF_True'")
	parser.add_argument("--percentageGPU", type=float, default=0.0, help="Amount of use the memory of the GPU. Type -> float. Example -> --percentageGPU=0.30")

	return parser.parse_args()

def searchModelInFile(model_name,file_pointer):

  for row in file_pointer:
    if model_name == row[0]:
      return True, row[1:]

  return False, []

def show_confussionMatrix(matrix,labels):

	row = matrix.shape[0]
	cols = matrix.shape[1]

	print('Real | Predicted | Amount')

	for i in range(0,row):
		for j in range(0,cols):
			print("%s | %s | %d" % (labels[i],labels[j],matrix[i,j]))

def WriteResultsModel(model,best_model_path,output_writer, x_test, y_test, steps, features, labels, labels_header):
  
	start_score_index = 0
	loss_outputs = list()
	accuracy_outputs = list()
	num_outputs = len(labels_header)

	# For CNN+LSTM or CNN+GRU, we had changed the input shape (n_samples, substeps, steps, features)
	if modelSplitPath[-1].split('-')[0].split("__")[0] in ["CNN_LSTM", "CNN_GRU"]:
		x_test = x_test.reshape((x_test.shape[0], 1, steps, features))
		print("x_test reshaped")

	# Get the predictions
	predictions = model.predict(x_test)

	# Check if the predictions var is a list (multiple outputs) or a numpy array (one output)
	if num_outputs > 1:

		start_score_index = 1

		# Modify y_test for multiple_outputs
		y_test_temp = list()
		for i in range(0,num_outputs):
			y_test_temp.append(y_test[:,i])

		y_test = y_test_temp

	else:
		# Convert to a list the predictions
		predictions = list([predictions])

		# Convert to a list the original outputs
		y_test = list([y_test])

	# Confusion matrix
	#cm = confusion_matrix(y_test.argmax(axis=1), predictions.argmax(axis=1))		

	# Evaluate test data
	score = model.evaluate(x_test, y_test, verbose=0)

	#print("RESULTS")
	#print("------------------------")
	#print("Confusion matrix")
	#show_confussionMatrix(cm,labels)
	#print("------------------------")
	#print("Score")
	#print("Test loss:", score[0])
	#print("Test accuracy:", str(round(score[1]*100,2)) + ' %')
	#print("------------------------")

	# Move index in the score array by '2' if the network has multiple outputs. Or by '1' if there is only one output ['loss','accuracy']
	j = start_score_index
	for i in range(0,num_outputs):

		loss_outputs.append(score[j])
		accuracy_outputs.append(str(round(score[j+1]*100,2)) + ' %')
		j = j + 2

	output_writer.writerow([best_model_path] + loss_outputs + accuracy_outputs)
	print("Model %s results saved correctly \n \n" % (best_model_path))

def loadOptions(pathOptions):

	dataframe = pd.read_csv(pathOptions)

	indexes = dataframe["indexes"].values[0].strip('][').replace("'","").replace(" ","").split(',')
	labels = dataframe["labels"].values[0].strip('][').replace("'","").replace(" ","").split(',')
	labels_header = dataframe["labels_header"].values[0].strip('][').replace("'","").replace(" ","").split(',')
	interpolate =  bool(dataframe["interpolate"].values[0])
	time_step =  int(dataframe["time_step"].values[0])
	num_features = len(indexes)
	num_classes = len(labels)

	return indexes, np.array(labels), labels_header, interpolate, time_step, num_features, num_classes;

def loadData(campaingPath, networkPath, indexes, labels, interpolate, time_step, num_features, scaler):

	pathData = os.path.join(campaingPath,"dataset")
	regions = os.listdir(pathData)
	num_regions = len(regions)

	# Sort by natural order
	regions.sort(key=natural_keys,reverse=False)

	sequences = []
	i = 1
	for region in regions:

		# open csv
		areadf = pd.read_csv(os.path.join(pathData,region))
		areadf = areadf[indexes].dropna(how='all')
		areadf = areadf.drop_duplicates()

		# interpolate data
		if(interpolate):
			areadf = areadf.interpolate(method='linear', axis=0).ffill().bfill()

		# Change time_step
		seq = areadf.values
		len_seq = len(seq)

		# Check if we have to extend or remove some elements at the end of the sequence
		n = time_step - len_seq
		if time_step >= len_seq:
			to_concat = np.repeat(seq[-1], n).reshape(num_features, n).transpose()
			seq = np.concatenate([seq, to_concat])
		else:
			seq = seq[:n]

		# Normalize
		seq = seq.reshape((1,time_step*num_features),order='F')
		seq = scaler.transform(seq)
		seq = np.reshape(seq, (time_step, num_features),order='F')

		print("---Cargando datos---")
		print("Progreso %d/%d" %(i,num_regions))
		print("Recinto %s cargado." %(region))
		i=i+1

		# Save in memory
		sequences.append(seq)

	x_data = np.array(sequences)

	# Check if the model needs to reshape the input (CNN)
	modelName = networkPath.split("\\")[-2]
	if modelName[0:8] == "CNN_LSTM":
		# Reshape due to CNN needs a vector of 4D
		x_data = x_data.reshape((x_data.shape[0], 1, time_step, num_features))

	return x_data, regions, num_regions

def loadDataTag(campaingPath, tags_name, labels_header, indexes, time_step, num_features, num_classes, scaler, interpolate):

	sequences = []
	targets = []
	path_tags = os.path.join(campaingPath, tags_name)

	# Read the test .csv
	tagDataFrame = pd.read_csv(path_tags)
	for label_header in labels_header:
		tagDataFrame = tagDataFrame[tagDataFrame[label_header] != -1]
	tagDataFrameName = tagDataFrame["id"]
	print(" '%s' cargado correctamente" %(tags_name))

	total_test = tagDataFrame.shape[0]

	# Get the sequence for each area (TEST)
	i = 1
	for row in tagDataFrame.values:

		region_path = row[0]
		areadf = pd.read_csv(os.path.join(campaingPath,'dataset',region_path))
		areadf = areadf[indexes].dropna(how='all')
		areadf = areadf.drop_duplicates()	

		if(interpolate):
			areadf = areadf.interpolate(method='linear', axis=0).ffill().bfill()

		# Change time_step
		seq = areadf.values
		len_seq = len(seq)
		n = time_step - len_seq

		# If we need more observations, we repeat the last value of the sequence
		if n > 0:
			to_concat = np.repeat(seq[-1], n).reshape(num_features, n).transpose()
			seq = np.concatenate([seq, to_concat])
		# If we don't need more observations, we remove the last ones
		elif n < 0:
			seq = seq[:n]		

		# Normalize
		seq = seq.reshape((1,time_step*num_features),order='F')
		seq = scaler.transform(seq)
		seq = np.reshape(seq, (time_step, num_features),order='F')

		print("---%s---" % (tags_name))
		print(campaingPath)
		print("Progreso %d/%d" %(i,total_test))
		print("Recinto %s cargado." %(region_path))
		i=i+1

		# Save in memory
		sequences.append(seq)
		targets.append(row[1:])

	x_data = np.array(sequences)
	y_data = np.array(targets)

	# convert class vectors to binary class matrices
	y_data = keras.utils.to_categorical(targets, num_classes)

	unique_samples_test, num_testSamples = np.unique(y_data, axis=0, return_counts=True)
	print("")
	print(tags_name)
	print(unique_samples_test)
	print(num_testSamples)
	print("Total: %d" %(num_testSamples.sum()))

	return x_data, y_data, tagDataFrameName, total_test

def LoadModel(modelPath):

	models = os.listdir(modelPath)
	models.sort(key=natural_keys,reverse=True)

	# Check if the model folder has 4 files (structure, logs, image and model)
	if len(models) == 4:
		best_model_name = models[3]
		modelPath = os.path.join(modelPath,best_model_name)

		model = load_model(modelPath)

		print('Model %s loaded' % (modelPath))
	else:
		print("Model folder hasn't got all the necessary files (structure, logs, image and model)! Aborting...")
		exit()

	return model, best_model_name

def TestModelTag(model,modelPath, x_test,y_test, num_regions, labels, labels_header, steps, features, num_classes, tagDataFrameName, output_path):
  
	name_outputs = list()
	real_tag_name = list()
	predicted_tag_name = list()
	num_outputs = len(labels_header)
	start_score_index = 0

	modelSplitPath = modelPath.split("\\")
	path_results = os.path.join("experiments",modelSplitPath[1],"results")

	# Check if the folder 'results' exists. If not, we'll create it
	if not os.path.exists(path_results):
		os.mkdir(path_results)

	# For CNN+LSTM or CNN+GRU, we had changed the input shape (n_samples, substeps, steps, features)
	if modelSplitPath[-1].split('-')[0].split("__")[0] in ["CNN_LSTM", "CNN_GRU"]:
		x_test = x_test.reshape((x_test.shape[0], 1, steps, features))
		print("x_test reshaped")

	# Get the predictions
	predictions = model.predict(x_test)

	# Check if the predictions var is a list (multiple outputs) or a numpy array (one output)
	if num_outputs > 1:

		start_score_index = 1

		# Modify y_test for multiple_outputs
		y_test_temp = list()
		for i in range(0,num_outputs):
			y_test_temp.append(y_test[:,i])
			real_tag_name.append("Real_" + str(i+1))
			predicted_tag_name.append("Predicted_" + str(i+1))

		y_test = y_test_temp

	else:

		# Convert to a list the predictions
		predictions = list([predictions])

		# Convert to a list the original outputs
		y_test = list([y_test])

		real_tag_name.append("Real")
		predicted_tag_name.append("Predicted")

	# Evaluate test data
	score = model.evaluate(x_test, y_test, verbose=0)

	with open(output_path, mode='w', newline="") as output_file:

		output_writer = csv.writer(output_file, delimiter=',')

		# Write output
		k = start_score_index
		for j in range(0,num_outputs):

			output_writer.writerow(['Name', 'Loss', 'Accuracy'])
			output_writer.writerow([modelPath,score[k],str(round(score[k+1]*100,2)) + ' %'])
			output_writer.writerow([])

			name_label = ['Real/Predicted_' + str(j+1)]
			name_label.extend(labels)
			output_writer.writerow(name_label)

			# Get the confussion matrix
			cm = confusion_matrix(y_test[j].argmax(axis=1), predictions[j].argmax(axis=1))		

			# Write confusion matrix in file
			for i in range(0,num_classes):
				row = [labels[i]]
				row.extend(cm[i,:])
				output_writer.writerow(row)

			output_writer.writerow([])

			k = k + 2

		# Convert the list output to numpy in order to get, for each output, the list of predictions for each sample
		predictions = np.array(predictions)
		y_test = np.array(y_test)

		# Write each area prediction
		output_writer.writerow([])

		output_writer.writerow(['Area'] + real_tag_name + predicted_tag_name)
		for i in range(0,num_regions):
			output_writer.writerow([tagDataFrameName.iloc[i]] + list(y_test[:,i].argmax(axis=1)) + list(predictions[:,i].argmax(axis=1)))

		# Closing the file
		output_file.close()

		print('Results saved in %s' % (output_path))

def TestModel(model, modelPath, x_test, regions, num_regions, labels, labels_header, steps, features, output_path):

	argPredictions = list()
	name_outputs = list()
	num_outputs = len(labels_header)

	modelSplitPath = modelPath.split("\\")
	path_results = os.path.join("experiments",modelSplitPath[1],"results")

	# Check if the folder 'results' exists. If not, we'll create it
	if not os.path.exists(path_results):
		os.mkdir(path_results)

	# For CNN+LSTM or CNN+GRU, we had changed the input shape (n_samples, substeps, steps, features)
	if modelSplitPath[-1].split('-')[0].split("__")[0] in ["CNN_LSTM", "CNN_GRU"]:
		x_test = x_test.reshape((x_test.shape[0], 1, steps, features))
		print("x_test reshaped")

	# Get the predictions
	predictions = model.predict(x_test)

	# Convert the 'predictions' var to a list if the number of outputs is equal to 1 (means, for one output, 'predictions' var won't be a list)
	if num_outputs == 1:
		predictions = list([predictions])

	predictions = np.array(predictions)

	with open(output_path, mode='w', newline="") as output_file:

		output_writer = csv.writer(output_file, delimiter=',')
		output_writer.writerow(['NameModel',modelPath])

		for label in labels_header:
			name_outputs.append(label)

		output_writer.writerow(['Name'] + name_outputs)

		for i in range(0,num_regions):
			output_writer.writerow([regions[i]] + list(predictions[:,i].argmax(axis=1)))

		# Closing the file
		output_file.close()
		print('Results saved in %s' % (output_path))

def TestModels(modelsExperiments,nameExperiment, campaingPath, tags_name):

	path_results = os.path.join("experiments",nameExperiment,"results")
	campaingName = campaingPath.split("\\")[-1]

	# Check if the folder 'results' exists. If not, we'll create it
	if not os.path.exists(path_results):
		os.mkdir(path_results)

	fileOutputName = os.path.join(path_results,campaingName+"_loss.csv")

	# Check if the file 'result_loss.csv' exists
	if os.path.exists(fileOutputName):
		fileOutputNameAux = os.path.join(path_results,campaingName+"_loss-temp.csv")

		# Update original file using temporal
		if os.path.exists(fileOutputNameAux):
			print("Replacing 'temp' to 'original")
			# Remove the original file
			os.remove(fileOutputName)
			# Rename the temporal file
			os.rename(fileOutputNameAux,fileOutputName)

		with open(fileOutputName,mode='r') as input_file:
			with open(fileOutputNameAux,mode='w',newline='') as output_file:

				# Write the header
				output_writer = csv.writer(output_file, delimiter=',')
				output_writer.writerow(["Name","Loss","Accuracy"])
				input_reader = csv.reader(input_file)

				total_experiments = len(modelsExperiments)
				actual_experiments = 0

				# Read each modelExperiment from each experiment in 'models' folder
				for modelExperiment in modelsExperiments:

					# Load scaler (normalize data)
					scalerPath = os.path.join("experiments",nameExperiment,"scalers",modelExperiment+"-scaler.pkl")
					scaler = load(open(scalerPath, 'rb'))
					print("Scaler: %s loaded" %(scalerPath))

					# Load options
					indexes, labels, labels_header, interpolate, time_step, num_features, num_classes = loadOptions(os.path.join("experiments",nameExperiment,"options",modelExperiment+".csv"))

					# Load data
					x_data, y_data, tagDataFrameName, num_regions = loadDataTag(campaingPath, tags_name, labels_header, indexes, time_step, num_features, num_classes, scaler, interpolate)
					x_data_aux = None

					# Get each model name from one experiment name
					modelsName = os.listdir(os.path.join("experiments",nameExperiment,"models",modelExperiment))

					actual_experiments = actual_experiments + 1
					total_modelsName = len(modelsName)
					actual_modelsName = 0

					# Load each model from one experiment
					for modelName in modelsName:

						print("PROGRESS")
						print("%d/%d" % (actual_experiments,total_experiments))

						actual_modelsName = actual_modelsName + 1
						print("%d/%d" % (actual_modelsName,total_modelsName))

						# Search model in file
						modelPath = os.path.join("experiments", nameExperiment, "models", modelExperiment, modelName)
						exists, score = searchModelInFile(modelPath,input_reader)

						# The model has already been tested
						if exists:
							print('Ignored the model %s' %(modelPath))
							output_writer.writerow([modelPath] + score)
						# Test the new model
						else:
							print("Loading %s" %(modelPath))
							model, best_model_name = LoadModel(modelPath)
							# Check if there is loaded one model
							if model is not None:
								WriteResultsModel(model,modelPath,output_writer,x_data,y_data,time_step,num_features,labels,labels_header)
							else:
								print("There is no model in %s" % (modelPath))
								continue
							k.clear_session()

		# Remove the original file
		os.remove(fileOutputName)
		# Rename the temporal file
		os.rename(fileOutputNameAux,fileOutputName)

		# Closing the files
		input_file.close()
		output_file.close()

	# Create a new one
	else:
		with open(fileOutputName,mode='w',newline='') as output_file:

			output_writer = csv.writer(output_file,delimiter=',')
			output_writer.writerow(["Name","Loss","Accuracy"])

			total_experiments = len(modelsExperiments)
			actual_experiments = 0

			# Read each modelExperiment from each experiment in 'models' folder
			for modelExperiment in modelsExperiments:

				# Load scaler (normalize data)
				scalerPath = os.path.join("experiments",nameExperiment,"scalers",modelExperiment+"-scaler.pkl")
				scaler = load(open(scalerPath, 'rb'))
				print("Scaler: %s loaded" %(scalerPath))

				# Load options
				indexes, labels, labels_header, interpolate, time_step, num_features, num_classes = loadOptions(os.path.join("experiments",nameExperiment,"options",modelExperiment+".csv"))

				# Load data
				x_data, y_data, tagDataFrameName, num_regions = loadDataTag(campaingPath, tags_name, labels_header, indexes, time_step, num_features, num_classes, scaler, interpolate)
				x_data_aux = None

				# Get each model name from one experiment name
				modelsName = os.listdir(os.path.join("experiments",nameExperiment,"models",modelExperiment))

				actual_experiments = actual_experiments + 1
				total_modelsName = len(modelsName)
				actual_modelsName = 0

				# Load each model from one experiment
				for modelName in modelsName:

					print("PROGRESS")
					print("%d/%d" % (actual_experiments,total_experiments))

					actual_modelsName = actual_modelsName + 1
					print("%d/%d" % (actual_modelsName,total_modelsName))

					# Load model
					modelPath = os.path.join("experiments", nameExperiment, "models", modelExperiment, modelName)
					model, best_model_name = LoadModel(modelPath)

					# Check if there is loaded one model
					if model is not None:
						WriteResultsModel(model,modelPath,output_writer,x_data,y_data,time_step,num_features,labels,labels_header)
					else:
						print("There is no model in %s" % (modelPath))
						continue
					k.clear_session()

		# Closing the file
		output_file.close()
		print("File %s saved correctly" %(fileOutputName))

def main():

	# Modify percentageGPU for the experiment
	args = defineArgParsers()
	configureKerasForGPU(args.percentageGPU)

	# Load single model
	if args.networkPath != '':

		# Load model
		tempPath = args.networkPath.split("\\")[0:5]
		modelPath = os.path.join("experiments", tempPath[1], "models", tempPath[3], tempPath[4])
		model, best_model_name = LoadModel(modelPath)

		# Load scaler (normalize data)
		scalerPath = os.path.join(tempPath[0],tempPath[1],"scalers",tempPath[3]+"-scaler.pkl")
		scaler = load(open(scalerPath, 'rb'))
		print("Scaler: %s loaded" %(scalerPath))

		# Load options
		indexes, labels, labels_header, interpolate, time_step, num_features, num_classes = loadOptions(os.path.join(tempPath[0],tempPath[1],"options",tempPath[3]+".csv"))

		# Load one campaing
		if args.campaingPath != '':
			# Load tag filename
			if args.tags_name != '':
				# Load data
				x_data, y_data, tagDataFrameName, num_regions = loadDataTag(args.campaingPath, args.tags_name, labels_header, indexes, time_step, num_features, num_classes, scaler, interpolate)
				TestModelTag(model, args.networkPath, x_data, y_data, num_regions, labels, labels_header, time_step, num_features, num_classes, tagDataFrameName, 
					os.path.join(tempPath[0],tempPath[1], "results", args.campaingPath.split("\\")[-1]+"-loss_predictions_" + args.tags_name))

			# Only predict without tags
			else:
				# Load data
				x_data, regions, num_regions = loadData(args.campaingPath, args.networkPath, indexes, labels, interpolate, time_step, num_features, scaler)
				TestModel(model, args.networkPath, x_data, regions, num_regions, labels, labels_header, time_step, num_features, os.path.join(tempPath[0],tempPath[1],"results",args.campaingPath.split("\\")[-1]+"-predictions.csv"))
		else:
			print("Error -> 'campaingPath' not specified")
			sys.exit()

	# Load multiple models
	else:

		if args.nameExperiment == '':
			print("Error -> 'nameExperiment' not specified")
			sys.exit()

		modelsExperiments = os.listdir(os.path.join("experiments",args.nameExperiment,"models"))

		# Load one campaing
		if args.campaingPath != '':
			# Load tag filename
			if args.tags_name != '':
				TestModels(modelsExperiments, args.nameExperiment, args.campaingPath, args.tags_name)
			else:
				print("Error -> 'tags_name' not specified")
				sys.exit()
		else:
			print("Error -> 'campaingPath' not specified")
			sys.exit()

if __name__ == '__main__':
	main()