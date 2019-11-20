from functions import defineArgParsersTest, addNDVI, natural_keys
from keras.models import load_model
import keras
import pandas as pd
import os
import csv
from sklearn.metrics import confusion_matrix
import numpy as np

def show_confussionMatrix(matrix,labels):

	row = matrix.shape[0]
	cols = matrix.shape[1]

	print('Real | Predicted | Amount')

	for i in range(0,row):
		for j in range(0,cols):
			print("%s | %s | %d" % (labels[i],labels[j],matrix[i,j]))

def searchModelInFile(model_name,file):

	for row in file:
		if model_name == row[0]:
			return True, row[1:]

	return False, []

def WriteResultsModel(best_model_path,output_writer, x_test, y_test, labels):

	# Load the best model for that experiment
	model = load_model(best_model_path)

	# Get the predictions
	predictions = model.predict(x_test)

	# Confusion matrix
	cm = confusion_matrix(y_test.argmax(axis=1), predictions.argmax(axis=1))

	# Evaluate test data
	score = model.evaluate(x_test, y_test, verbose=0)

	# Clean terminal
	print('\033c')

	print("RESULTS")
	print("------------------------")
	print("Confusion matrix")
	show_confussionMatrix(cm,labels)
	print("------------------------")
	print("Score")
	print('Test loss:', score[0])
	print('Test accuracy:', score[1])
	print("------------------------")

	output_writer.writerow([best_model_path, score[0], score[1]])
	print("Model %s results saved correctly" % (best_model_path))

def testModel(args):

	labels = args.labels.split(',')
	num_classes = len(labels)

	# Get the path where the csv is located
	parentPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	testFilePath= os.path.join(parentPath,args.datasets_path,args.testDataName)

	# Load csv test
	testDataFrame = pd.read_csv(testFilePath)
	print('csv for testing loaded')

	# Get a numpy array of the dataframe
	test_n = testDataFrame.to_numpy()

	# Split the input and output values
	x_test = test_n[:,:-1]
	y_test = test_n[:,-1]

	# convert class vectors to binary class matrices
	y_test = keras.utils.to_categorical(y_test, num_classes)

	# Add NDVI
	#x_test = addNDVI(x_test)

	# Number of features
	num_features_input = x_test.shape[1]

	# Get a list of all saved models
	ExperimentPath = os.path.join(args.model_parameters_path)
	models = os.listdir(ExperimentPath)
	models.sort(key=natural_keys,reverse=True)
	# Remove the 'log' folder
	models = models[1:]

	# Load the best model for that experiment
	model = load_model(os.path.join(ExperimentPath,models[0]))

	# Get the predictions
	predictions = model.predict(x_test)

	with open(args.experiment_name + '-' + args.output_name_predictions, mode='w') as output_file:

		output_writer = csv.writer(output_file, delimiter=',')

		# Evaluate test data
		score = model.evaluate(x_test, y_test, verbose=0)

		output_writer.writerow(['Name', 'Loss', 'Accuracy'])
		output_writer.writerow([os.path.join(args.model_parameters_path,models[0]),score[0], score[1]])

		output_writer.writerow([])

		name_label = ['Real/Predicted']
		name_label.extend(labels)
		output_writer.writerow(name_label)

		# Confusion matrix
		cm = confusion_matrix(y_test.argmax(axis=1), predictions.argmax(axis=1))

		# Write confusion matrix in file
		for i in range(0,num_classes):

			row = [labels[i]]
			row.extend(cm[i,:])
			output_writer.writerow(row)

		# Write each area prediction
		num_samples = y_test.shape[0]
		output_writer.writerow([])
		output_writer.writerow(['Area', 'Real', 'Predicted'])
		for i in range(0,num_samples):
			output_writer.writerow([i+1, labels[np.argmax(y_test[i])],labels[np.argmax(predictions[i])]])

		# Clean terminal
		print('\033c')

		print("RESULTS")
		print("------------------------")
		print("Confusion matrix")
		show_confussionMatrix(cm,labels)
		print("------------------------")
		print("Score")
		print('Test loss:', score[0])
		print('Test accuracy:', score[1])
		print("------------------------")

def testModels(args):

	labels = args.labels.split(',')
	num_classes = len(labels)

	# Get the path where the csv is located
	parentPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	testFilePath= os.path.join(parentPath,args.datasets_path,args.testDataName)

	# Load csv test
	testDataFrame = pd.read_csv(testFilePath)
	print('csv for testing loaded')

	# Get a numpy array of the dataframe
	test_n = testDataFrame.to_numpy()

	# Split the input and output values
	x_test = test_n[:,:-1]
	y_test = test_n[:,-1]

	# convert class vectors to binary class matrices
	y_test = keras.utils.to_categorical(y_test, num_classes)

	# Add NDVI
	#x_test = addNDVI(x_test)

	# Number of features
	num_features_input = x_test.shape[1]

	fileOutputName = args.experiment_name + '-' + args.output_name_loss

	# Check if the file already exists
	if os.path.isfile(fileOutputName):
		
		fileOutputNameAux = 'temp -' + args.experiment_name + '-' + args.output_name_loss

		with open(fileOutputName,mode='r') as input_file:
			with open(fileOutputNameAux,mode='w') as output_file:

				# Write the header
				output_writer = csv.writer(output_file, delimiter=',')
				output_writer.writerow(input_file.readline().rstrip('\n').split(','))
				input_reader = csv.reader(input_file)

				# List of models parameters
				models_parameters = os.listdir(os.path.join(args.experiment_folder,args.experiment_name))
				for model_parameters in models_parameters:

					# Get a list of all saved models and return the path where is the best one saved
					ExperimentPath = os.path.join(args.experiment_folder,args.experiment_name,model_parameters)
					models = os.listdir(ExperimentPath)
					models.sort(key=lambda x: os.path.getmtime(os.path.join(ExperimentPath,x)),reverse=True)

					# Get the path where the best model is located
					best_model_path = os.path.join(args.experiment_folder,args.experiment_name,
						model_parameters,models[0])

					# Check if the model has already tested
					exists, score = searchModelInFile(best_model_path,input_reader)

					# The model has already tested
					if exists:
						print('Ignored the model %s' %(best_model_path))
						output_writer.writerow([best_model_path, score[0], score[1]])
					# Test the new model
					else:
						WriteResultsModel(best_model_path,output_writer,x_test,y_test,labels)

		# Remove the original file
		os.remove(fileOutputName)
		# Rename the temporal file
		os.rename(fileOutputNameAux,fileOutputName)

		# Closing the files
		input_file.close()
		output_file.close()

	else:

		with open(fileOutputName,mode='a') as output_file:

			output_writer = csv.writer(output_file, delimiter=',')
			output_writer.writerow(['Name', 'Loss', 'Accuracy'])

			# List of models parameters
			models_parameters = os.listdir(os.path.join(args.experiment_folder,args.experiment_name))
			for model_parameters in models_parameters:

				# Get a list of all saved models
				ExperimentPath = os.path.join(args.experiment_folder,args.experiment_name,model_parameters)
				models = os.listdir(ExperimentPath)
				models.sort(key=lambda x: os.path.getmtime(os.path.join(ExperimentPath,x)),reverse=True)

				best_model_path = os.path.join(args.experiment_folder,args.experiment_name,
						model_parameters,models[0])

				WriteResultsModel(best_model_path,output_writer, x_test, y_test,labels)

		# Closing the file
		output_file.close()

def main():

	args = defineArgParsersTest()

	if args.model_parameters_path == '':
		testModels(args)
	else:
		testModel(args)

if __name__ == "__main__":
	main()