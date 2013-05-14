#!/usr/bin/env python

"""

@author:
    slu

@description:
    Overlap tool - The tool would be something that we can apply to things 
    that need secondary animation like hair, tails, etc.. When applied it will 
    perform the secondary animation on the joints applied and have a node in which 
    we can can control the variables such as gravity, stiffness, dampening, speed, 
    etc... and a blend control to be able to dial in and out of specified poses we may 
    assign to the joints during the performance.  
    so in theory, sometimes we may be letting the simulation take care of the 
    secondary and other times we may want to control specific poses. 
    
@departments:
    - Animation

@applications:
    - Maya

"""

#----------------------------------------------------------------------------#
#----------------------------------------------------------------- IMPORTS --#

# Built-in
import overlap_tool
import maya.cmds as mc
import maya.mel as mm
from pymel.all import *

# External
import ani_tools.rmaya.ani_library as ani_lib
from maya_tools.ui.gui_tool_kit import *

#---------------------------------------------------------------------------------#
# Constants
#---------------------------------------------------------------------------------#

def stretch_chain(nameOfDynCurve, baseJoint, endJoint):
	curveInfoNode=str(arclen(nameOfDynCurve, ch=1))
	#Create curve info node
	curveInfoNode=str(rename(curveInfoNode,
                (baseJoint + "CurveInfoNode")))
	#Create mult/div node
	nameOfUtilityNode=str(shadingNode('multiplyDivide', asUtility=True))
	nameOfUtilityNode=str(rename(nameOfUtilityNode,
                (baseJoint + "MultiDivNode")))
	#Create condition node
	nameOfConditionNode=shadingNode('condition', asUtility=True)
	nameOfConditionNode=rename(nameOfConditionNode,
                (baseJoint + "ConditionNode"))
	#Setup multi/div node
	setAttr((nameOfUtilityNode + ".operation"), 2)
	connectAttr((curveInfoNode + ".arcLength"),
                    (nameOfUtilityNode + ".input1X"), force=True)
	setAttr((nameOfUtilityNode + ".input2X"),(getAttr(curveInfoNode + ".arcLength")))
	#Setup condition node
	connectAttr((nameOfUtilityNode + ".outputX"),
                    (str(nameOfConditionNode) + ".firstTerm"), force=True)
	connectAttr((nameOfUtilityNode + ".outputX"),
                    (str(nameOfConditionNode) + ".colorIfFalseR"),force=True)
	setAttr((str(nameOfConditionNode) + ".operation"), 4)
	setAttr((str(nameOfConditionNode) + ".secondTerm"), 1.0)
	setAttr((str(nameOfConditionNode) + ".colorIfTrueR"), 1.0)
	#Initial selection going into the while loop
	select(baseJoint)
	currentJoint=baseJoint
	#Will loop through all the joints between the base and end by pickwalking through them.
	#The loop connects the scaleX of each joint to the output of the multi/div node.
	while currentJoint != endJoint:
		connectAttr((str(nameOfConditionNode) + ".outColorR"),
	                    (currentJoint + ".scaleX"), f=True)
		pickWalk(d='down')
		sel=mc.ls(selection=True)
		currentJoint=sel[0]

def add_dynamic_attributes(jointCtrlObj):
	addAttr(jointCtrlObj,
	        min=0,ln='stiffness',max=1,keyable=True,at='double',dv=0.001)
	addAttr(jointCtrlObj,
                min=0,ln='lengthFlex',max=1,keyable=True,at='double',dv=0)
	addAttr(jointCtrlObj,
                min=0,ln='damping',max=100,keyable=True,at='double',dv=0)
	addAttr(jointCtrlObj,
                min=0,ln="drag",max=1,keyable=True,at='double',dv=.05)
	addAttr(jointCtrlObj,
                min=0,ln='friction',max=1,keyable=True,at='double',dv=0.5)
	addAttr(jointCtrlObj,
                min=0,ln="gravity",max=10,keyable=True,at='double',dv=1)
	addAttr(jointCtrlObj,
                min=0,ln="controllerSize",max=100,keyable=True,at='double',dv=0.5)
	addAttr(jointCtrlObj, ln="turbulenceCtrl", at='bool', keyable=True)
	setAttr((jointCtrlObj + ".turbulenceCtrl"),
                lock=True)
	addAttr(jointCtrlObj,
                min=0,ln="strength",max=1,keyable=True,at='double',dv=0)
	addAttr(jointCtrlObj,
                min=0,ln="frequency",max=2,keyable=True,at='double',dv=0.2)
	addAttr(jointCtrlObj,
                min=0,ln="speed",max=2,keyable=True,at='double',dv=0.2)

def lock_and_hide_attr(jointCtrlObj):
	attrs = ['tx', 'ty', 'tz',
	         'rx', 'ry', 'rz',
	         'sx', 'sy', 'sz',]
	for attr in attrs:
		setAttr('{obj}.{attr}'.format(obj = jointCtrlObj, attr = attr), 
	        	lock=True, 
	                keyable=False
		)
		
def connect_controller_to_system(ctrl, system, attrs):
	""" Connect the system attributes to the controllers.
	Args:
		ctrl - (str)
			Name of the controller
		system - (str)
			Name of the system to connect
		attrs - (dict)
			attributes to connect.  The key represents
			the controllers attr and the value represents
			the systems attr.

	"""
	for c_attr, s_attr in attrs.iteritems():
		connectAttr(
		        '{ctrl}.{attr}'.format(ctrl=ctrl, attr=c_attr), 
		        '{system}.{attr}'.format(system=system, attr=s_attr), 
		        f=True
		)

#---------------------------------------------------------------------------------#
# Classes
#---------------------------------------------------------------------------------#
def create_dynamic_chain():
	sel=mc.ls(selection=True)
	#Store the current selection into an string array.
	#Store the name of the base and end joints into strings.
	baseJoint=sel[0]
	endJoint=sel[1]
	#Create a vector array to store the world space coordinates of the joints.
	jointPos=[]
	#String variable to house current joint being queried in the while loop.
	currentJoint=baseJoint
	#Counter integer used in the while loop to determine the proper index in the vector array.
	counter=0
	#Check to ensure proper selection
	if not ((objectType(baseJoint, isType="joint")) and 
	        (objectType(endJoint, isType="joint"))):
		mel.warning("Please select a base and tip joint to make dynamic.")
	else:
		select(baseJoint)
		#Initial selection going into the while loop/
		#Will loop through all the joints between the base and end by pickwalking through them.
		#The loop stores the world space of each joint into $jointPos as it iterates over them.
		while currentJoint != endJoint:
			#jointPos[counter]=joint(currentJoint,q=1,p=1,a=1)
			jointPos.append(joint(currentJoint, q=1, p=1, a=1))
			pickWalk(d='down')
			sel=mc.ls(selection=True)
			currentJoint=sel[0]
			counter+=1
		
		sel=mc.ls(selection=True)
		#Theses 3 lines store the position of the end joint that the loop will miss.
		currentJoint=sel[0]
		jointPos.append(joint(currentJoint, q=1,p=1,a=1))
		#Now that $jointPos[] holds the world space coords of our joints, we need to build a cv curve
		#with points at each XYZ coord.
		#This string will house the command to create our curve.
		buildCurve="curve -d 1 "
		#Another counter integer for the for loop
		cvCounter=0
		#Loops over and adds the position of each joint to the buildCurve string.
		for i in range(cvCounter, counter + 1):
			buildCurve = "{curve} -p {jpos}".format(
				curve = buildCurve,
				jpos = " ".join([str(pos) for pos in jointPos[i]])
			)
		buildCurve = buildCurve + ";"
		#Adds the end terminator to the build curve command
		#Evaluates the $buildCurve string as a Maya command. (creates the curve running through the joints)
		nameOfCurve = str(mel.eval(buildCurve))
		#Make curve dynamic.
		select(nameOfCurve)
		#mel.makeCurvesDynamicHairs()
		mm.eval('makeCurvesDynamicHairs false false true')
		#Determine what the name of the dynamic curve is
		nameOfDynCurve=''
		sizeOfString=len(nameOfCurve)
		sizeOfString+=1
		nameOfDynCurve=nameOfCurve[5:sizeOfString]
		sizeOfString=int(nameOfDynCurve)
		sizeOfString+=1
		nameOfDynCurve=("curve" + str(sizeOfString))
		#Create Tip Constraint
		nameOfHairConstraint=[]
		if checkBoxGrp('tipConstraintCheckbox',q=1,value1=1):
			select((nameOfDynCurve + ".cv[" + str(cvCounter) + "]"), r=True)
			mel.createHairConstraint(0)
			selection=pickWalk(d='up')
			nameOfHairConstraint.append(selection[0])
			nameOfHairConstraint[0]=str(rename(nameOfHairConstraint[0],
				(baseJoint + "TipConstraint")))
			
		curveInfoNode=''
		#Make Joint Chain Stretchy
		nameOfUtilityNode=''
		if checkBoxGrp('stretchCheckbox',q=1,value1=1):
			stretch_chain(nameOfDynCurve, baseJoint, endJoint)
			
		select(nameOfDynCurve)
		#Display Current Position of Hair
		mel.displayHairCurves("current", 1)
		#Determine name of follicle node
		select(nameOfCurve)
		nameOfFollicle=pickWalk(d='up')
		#Create Joint Chain Controller Object
		jointCtrlObjArray=[]
		jointCtrlObjArray.append(str(createNode('implicitSphere')))
		jointCtrlObjArray=pickWalk(d='up')
		jointCtrlObj=jointCtrlObjArray[0]
		#Point Constrain Control Object to the end joint
		pointConstraint(endJoint,jointCtrlObj)
		#Add attributes to controller for the dynamics
		add_dynamic_attributes(jointCtrlObj)
		
		#Determine what the name of the hair system is
		nameOfHairSystem=''
		sizeOfString=len(nameOfFollicle[0])
		sizeOfString+=1
		nameOfHairSystem=nameOfFollicle[0][8:sizeOfString]
		sizeOfString=int(nameOfHairSystem)
		nameOfHairSystem=("hairSystemShape" + str(sizeOfString))
		#Add special attribute to house name of hairSystem
		addAttr(jointCtrlObj,
			ln='nameOfHairShapeNode',dt="string",keyable=False)
		setAttr((jointCtrlObj + ".nameOfHairShapeNode"),(nameOfHairSystem),
			lock=True,type="string")
		#Add special attribute to house name of follicle
		addAttr(jointCtrlObj,
			ln='nameOfFollicleNode',dt="string",keyable=False)
		setAttr((jointCtrlObj + ".nameOfFollicleNode"),(nameOfFollicle[0]),
			lock=True,type="string")
		#Add special attribute to house name of dynamic curve
		addAttr(jointCtrlObj,
			ln='nameOfDynCurve',dt="string",keyable=False)
		setAttr((jointCtrlObj + ".nameOfDynCurve"),(nameOfDynCurve),
			lock=True,type="string")
		#Add special attribute to house name of tip constraint
		if nameOfHairConstraint:
			addAttr(jointCtrlObj,
				ln='nameOfTipConstraint',dt="string",keyable=False)
			setAttr((jointCtrlObj + ".nameOfTipConstraint"),(nameOfHairConstraint[0]),
				lock=True,type="string")
		#Add special attribute to house name of multi/div node
		addAttr(jointCtrlObj,
			ln='nameOfMultiDivNode',dt="string",keyable=False)
		setAttr((jointCtrlObj + ".nameOfMultiDivNode"),(nameOfUtilityNode),
			lock=True,type="string")
		#Add special attribute to base and end joint names
		addAttr(jointCtrlObj,
			ln='baseJoint',dt="string",keyable=False)
		addAttr(jointCtrlObj,
			ln='endJoint',dt="string",keyable=False)
		setAttr((jointCtrlObj + ".baseJoint"),(baseJoint),
			lock=True,type="string")
		setAttr((jointCtrlObj + ".endJoint"),(endJoint),
			lock=True,type="string")
		#Add special attribute to house baking state
		addAttr(jointCtrlObj,
			ln='bakingState',at='bool')
		#Add special attribute to house stretchy state
		addAttr(jointCtrlObj,
			ln='isStretchy',at='bool')
		if checkBoxGrp('stretchCheckbox',q=1,value1=1):
			setAttr((jointCtrlObj + ".isStretchy"), 1)
		
		#Overide the Hair dynamics so that the follicle controls the curve dynamics
		select(nameOfFollicle)
		nameOfFollicle=pickWalk(d='down')
		setAttr((nameOfFollicle[0] + ".overrideDynamics"), 1)
		
		#Set the dynamic chain to hang from the base joint (not both ends)
		setAttr((nameOfFollicle[0] + ".pointLock"), 1)
		 
		#Connect attributes on the controller sphere to the follicle node
		ctrl_to_follicle_attrs = {
		        'stiffness' : 'stiffness',
		        'lengthFlex' : 'lengthFlex',
		        'damping' : 'damp'
		}
		connect_controller_to_system(jointCtrlObj, nameOfFollicle[0], ctrl_to_follicle_attrs)
	
		#Connect attribute on the controller sphere to the hair system node
		ctrl_to_hairsystem_attrs = {
		        'drag' : 'drag',
		        'friction' : 'friction',
		        'gravity' : 'gravity',
		        'strength' : 'turbulenceStrength',
		        'frequency' : 'turbulenceFrequency',
		        'speed' : 'turbulenceSpeed',
		}
		connect_controller_to_system(jointCtrlObj, nameOfHairSystem, ctrl_to_hairsystem_attrs)
		
		#Connect scale of controller to the size attr
		connectAttr((jointCtrlObj + ".controllerSize"),
		            (jointCtrlObj + ".scaleX"), f=True)
		connectAttr((jointCtrlObj + ".controllerSize"), 
		            (jointCtrlObj + ".scaleY"), f=True)
		connectAttr((jointCtrlObj + ".controllerSize"), 
		            (jointCtrlObj + ".scaleZ"), f=True)
		
		#Lock And Hide Attributes on Control Object.
		lock_and_hide_attr(jointCtrlObj)
		
		#Build the splineIK handle using the dynamic curve.
		select(baseJoint,endJoint,nameOfDynCurve)
		nameOfIKHandle=ikHandle(ccv=False,sol='ikSplineSolver')
		nameOfIKHandle[0]=str(rename(nameOfIKHandle[0],
			(baseJoint + "ikHandle")))
		#Rename Ctrl Obj
		jointCtrlObj=str(rename(jointCtrlObj,
			(baseJoint + "DynChainControl")))
		#Parent follicle node to the parent of the base joint
		#This will attach the joint chain to the rest of the heirarchy if there is one.
		select(nameOfFollicle[0])
		pickWalk(d='up')
		follicleGrpNode=pickWalk(d='up')
		#Determine parent of base joint
		select(baseJoint)
		parentOfBaseJoint=pickWalk(d='up')
		if parentOfBaseJoint[0] == baseJoint:
			mel.warning("No parent hierarchy was found for the dynamic chain.\n")
		else:
			parent(follicleGrpNode,parentOfBaseJoint)
			# Parent the follicle into heirarchy
			parent(nameOfDynCurve, w=True)
			
		sliderStiffness=float(floatSliderGrp('sliderStiffness',query=1,value=1))
		# Set dynamic chain attributes according to creation options
		sliderDamping=float(floatSliderGrp('sliderDamping',query=1,value=1))
		sliderDrag=float(floatSliderGrp('sliderDrag',query=1,value=1))
		setAttr((baseJoint + "DynChainControl.stiffness"),
			sliderStiffness)
		setAttr((baseJoint + "DynChainControl.damping"),
			sliderDamping)
		setAttr((baseJoint + "DynChainControl.drag"),
			sliderDrag)
		# Group the dynamic chain nodes
		nameOfGroup=str(group(jointCtrlObj,nameOfDynCurve,nameOfIKHandle[0],nameOfHairSystem,
			name=(baseJoint + "DynChainGroup")))
		# If the chain has a tip constraint, then parent this under the main group to keep things tidy.
		if checkBoxGrp('tipConstraintCheckbox',q=1,value1=1):
			parent(nameOfHairConstraint[0],nameOfGroup)
			
		# Turn the visibility of everything off to reduce viewport clutter.
		items_to_hide = [
		        nameOfDynCurve,
		        nameOfIKHandle[0],
		        follicleGrpNode[0],
		        nameOfHairSystem,
		]
		change_visibility(items_to_hide, visibility=False)
		
		# Delete useless 'hairsystemoutputcurves' group node
		select(nameOfHairSystem)
		nameOfGarbageGrp=pickWalk(d='up')
		delete(nameOfGarbageGrp[0] + "OutputCurves")
		# Select dynamic chain controller for user
		select(baseJoint + "DynChainControl")
		# Print feedback for user
		print "Dynamic joint chain successfully setup!\n"
		

def change_visibility(items, visibility):
	[setAttr("{0}.visibility".format(item), visibility) for item in items]

#///////////////////////////////////////////////////////////////////////////////////////
#								Collisions Procedure
#///////////////////////////////////////////////////////////////////////////////////////
def collideWithChain():
	sel=mc.ls(selection=True)
	controllers=[]
	colliders=[]
	#Progress Window Amount
	amount=0
	numberOfObjects=len(sel)
	i=0
	progressWindow(status="Preparing: 0%",
		title="CGToolkit's Dyn Chain Collisions:",
		maxValue=100,
		minValue=0,
		isInterruptable=True,
		progress=amount)
	#Loop through the whole selection and split up
	#into $controllers or $colliders
	for obj in sel:
		i+=1
		# Check if the dialog has been cancelled
		if progressWindow(query=1,isCancelled=1):
			break
			# Check if end condition has been reached
			
		if progressWindow(query=1,progress=1)>=100:
			break
			
		amount=((100 / numberOfObjects) * i)
		progressWindow(edit=1,progress=amount)
		#Find the current index in controllers array
		pos=len(controllers)
		#If obj is a controller
		if mel.attributeExists("nameOfHairShapeNode", obj):
			controllers[pos]=str(obj)
			#Add to controller list
			
		
		else:
			shapeNode=listRelatives(path=obj,s=1)
			#Get the shape node of obj
			#Find current index in collider array
			pos=len(colliders)
			#Check if shape node is a mesh, or a nurbs surface
			if (objectType(shapeNode[0],
				isType="mesh")) or (objectType(shapeNode[0],
				isType="nurbsSurface")):
				colliders[pos]=str(obj)
				
			
		
	progressWindow(edit=1,status="Connecting Colliders: 0%")
	numberOfObjects=len(controllers)
	i=0
	#For every controller that was selected...
	for chainCtrl in controllers:
		i+=1
		# Check if the dialog has been cancelled
		if progressWindow(query=1,isCancelled=1):
			break
			# Check if end condition has been reached
			
		if progressWindow(query=1,progress=1)>=100:
			break
			
		amount=((100 / numberOfObjects) * i)
		progressWindow(edit=1,progress=amount)
		#Get the name of the hair shape node
		hairShape=str(getAttr(str(chainCtrl) + ".nameOfHairShapeNode"))
		#For every NURBS or polygon surface that was selected...
		for collider in colliders:
			nameofGeoConnector=str(createNode('geoConnector'))
			#Create geoConnector node and store it's name into a variable
			#Get the shape node of collider
			objShape=listRelatives(path=collider,s=1)
			#Connect all the necessary attributes to make the surface collide
			connectAttr((objShape[0] + ".message"),(nameofGeoConnector + ".owner"))
			connectAttr((objShape[0] + ".worldMatrix[0]"),(nameofGeoConnector + ".worldMatrix"))
			connectAttr((objShape[0] + ".outMesh"),(nameofGeoConnector + ".localGeometry"))
			connectAttr((hairShape + ".collisionResilience"),
				na=(nameofGeoConnector + ".resilience"))
			connectAttr((hairShape + ".collisionFriction"),
				na=(nameofGeoConnector + ".friction"))
			connectAttr((hairShape + ".collisionGeometry"),
				na=(nameofGeoConnector + ".sweptGeometry"))
			connectAttr('time1.outTime',(nameofGeoConnector + ".currentTime"))
			#Print output to the user for each connected collider.
			print str(obj) + " has been set to collide with " + str(chainCtrl) + "\n"
			
		
	progressWindow()
	

#///////////////////////////////////////////////////////////////////////////////////////
#								BAKING PROCEDURE
#///////////////////////////////////////////////////////////////////////////////////////
def bakeDynChain():
	initialSel=mc.ls(selection=True)
	#Declare necessary variables
	allCtrls=[]
	i=0
	amount=0
	#Filter selection to contain only dynamic chain controllers.
	for obj in initialSel:
		if mel.attributeExists("nameOfHairShapeNode", obj):
			allCtrls[i]=str(obj)
			i+=1
			
		
	progressWindow(status="Baking Joint Chains:",
		title="CGToolkit's Dynamic Joint Chain:",
		maxValue=100,
		minValue=0,
		isInterruptable=True,
		progress=amount)
	#Create a progress window
	#Construct frame range variable
	frameRangeToBake=''
	startFrame=float(intField('startFrame',query=1,value=1))
	endFrame=float(intField('endFrame',query=1,value=1))
	frameRangeToBake=("\"" + str(startFrame) + ":" + str(endFrame) + "\"")
	j=1
	#For all of the selected chain controllers.
	for obj in allCtrls:
		if progressWindow(query=1,isCancelled=1):
			break
			# Check if the dialog has been cancelled
			# Check if end condition has been reached
			
		if progressWindow(query=1,progress=1)>=100:
			break
			
		amount=((100 / i) * j)
		progressWindow(edit=1,progress=amount)
		progressWindow(edit=1,status=("Baking chain " + str(j) + " of " + str(i) + " :"))
		j+=1
		chainCtrl=str(obj)
		baseJoint=str(getAttr(chainCtrl + ".baseJoint"))
		endJoint=str(getAttr(chainCtrl + ".endJoint"))
		bakingJoints="{\""
		currentJoint=[]
		currentJoint[0]=endJoint
		#Determine joints to be baked
		while currentJoint[0] != baseJoint:
			bakingJoints=(bakingJoints + currentJoint[0] + "\", \"")
			select(currentJoint[0])
			currentJoint=pickWalk(d='up')
			
		
		bakingJoints=(bakingJoints + baseJoint + "\"}")
		#Add the base joint that the while loop will miss
		#Concatenate the bake simulation command with the necessary joint names.
		bakingJoints=("bakeResults -simulation true -t " + frameRangeToBake + " -sampleBy 1 -disableImplicitControl true -preserveOutsideKeys true -sparseAnimCurveBake false -controlPoints false -shape true" + bakingJoints)
		#Evaluate the $bakingJoints string to bake the simulation.
		mel.eval(bakingJoints)
		#Tell control object that joints are baked.
		setAttr((chainCtrl + ".bakingState"),
			1)
		#Print feedback to user
		print "All joints controlled by " + chainCtrl + " have now been baked!\n"
		
	progressWindow()
	

#///////////////////////////////////////////////////////////////////////////////////////
#								DELETE DYNAMICS PROCEDURE
#///////////////////////////////////////////////////////////////////////////////////////
def deleteDynChain():
	initialSel=mc.ls(selection=True)
	#Declare necessary variables
	chainCtrl=initialSel[0]
	error=0
	#Check that controller is selected.
	if not mel.attributeExists("bakingState", chainCtrl):
		error=1
		mel.warning("Please select a chain controller. No dynamics were deleted.")
		
	
	elif ((getAttr(chainCtrl + ".bakingState")) == 0) and ((getAttr(chainCtrl + ".isStretchy")) == 1):
		result=str(confirmDialog(title="Delete Dynamics Warning",
			cancelButton="Cancel",
			defaultButton="Cancel",
			button=["Continue Anyway", 
				"Cancel"],
			message="Deleting the dynamics on a stretchy chain may cause it to collapse. Please bake the joint chain before deleting.",
			dismissString="Cancel"))
		#Check if joints have been baked.
		if result == "Cancel":
			error=1
			mel.warning("Dynamics were not deleted for " + chainCtrl)
			
		
	if error == 0:
		hairSystemName=[]
		#Delete Hair System Node
		hairSystemName[0]=str(getAttr(chainCtrl + ".nameOfHairShapeNode"))
		select(hairSystemName[0])
		hairSystemName=pickWalk(d='up')
		delete(hairSystemName)
		#Delete Follicle Node
		follicleNode=[]
		follicleNode[0]=str(getAttr(chainCtrl + ".nameOfFollicleNode"))
		select(follicleNode[0])
		follicleNode=pickWalk(d='up')
		delete(follicleNode)
		#Delete Dynamic Hair Curve
		delete(getAttr(chainCtrl + ".nameOfDynCurve"))
		#Delete Tip Constraint
		if (getAttr(chainCtrl + ".nameOfTipConstraint")) != "":
			delete(getAttr(chainCtrl + ".nameOfTipConstraint"))
			#Delete Multi/Div Node
			
		if (getAttr(chainCtrl + ".nameOfMultiDivNode")) != "":
			delete(getAttr(chainCtrl + ".nameOfMultiDivNode"))
			#Delete IK Handle
			
		baseJoint=str(getAttr(chainCtrl + ".baseJoint"))
		delete(baseJoint + "ikHandle")
		#Delete control object
		delete(chainCtrl)
		#Print feedback to the user.
		print "Dynamics have been deleted from the chain.\n"
		
	

#///////////////////////////////////////////////////////////////////////////////////////
#								MAIN WINDOW
#///////////////////////////////////////////////////////////////////////////////////////
def main():
	if window('dynChainWindow',q=1,ex=1):
		deleteUI('dynChainWindow')
		#Main Window
		
	window('dynChainWindow',h=200,w=360,title="RFX Overlapping Tool")
	scrollLayout(hst=0)
	columnLayout('dynChainColumn')
	#Dynamic Chain Creation Options Layout
	frameLayout('creationOptions',h=130,
		borderStyle='etchedOut',
		collapsable=True,
		w=320,
		label="Dynamic Chain Creation Options:")
	frameLayout('creationOptions',e=1,cl=True)
	columnLayout(cw=300)
	#Stiffness
	floatSliderGrp('sliderStiffness',min=0,max=1,
		cw3=(60, 60, 60),
		precision=3,
		value=0.001,
		label="Stiffness:",
		field=True,
		cal=[(1, 'left'), (2, 'left'), (3, 'left')])
	#Damping
	floatSliderGrp('sliderDamping',min=0,max=100,
		cw3=(60, 60, 60),
		precision=3,
		value=0.05,
		label="Damping:",
		field=True,
		cal=[(1, 'left'), (2, 'left'), (3, 'left')])
	#Drag
	floatSliderGrp('sliderDrag',min=0,max=1,
		cw3=(60, 60, 60),
		precision=3,
		value=0.0,
		label="Drag:",
		field=True,
		cal=[(1, 'left'), (2, 'left'), (3, 'left')])
	#Tip Constraint Checkbox
	separator(h=20,w=330)
	checkBoxGrp('tipConstraintCheckbox',cw=(1, 150),label="Create Tip Constraint : ")
	checkBoxGrp('stretchCheckbox',cw=(1, 150),label="Allow Joint Chain to Stretch: ")
	#separator -h 20  -w 330;
	setParent('..')
	setParent('..')
	#Button Layouts
	rowColumnLayout(nc=2,cw=[(1, 175), (2, 150)])
	text("Select base joint, shift select tip: ")
	button(c=lambda *args: overlap_tool.create_dynamic_chain(),label="Make Dynamic")
	text("Select control, shift select collider(s): ")
	button(c=lambda *args: overlap_tool.collideWithChain(),label="Make Collide")
	text("Select control: ")
	button(c=lambda *args: overlap_tool.deleteDynChain(),label="Delete Dynamics")
	setParent('..')
	#Bake Animation Layouts
	separator(h=20,w=330)
	text("                               -Bake Joint Animation-")
	rowColumnLayout('bakeRowColumn',nc=3,cw=[(1, 100), (2, 100)])
	text("Start Frame: ")
	text("End Frame:")
	text("Select Control:")
	intField('startFrame')
	intField('endFrame',value=400)
	button(c=lambda *args: cgTkDynChain.bakeDynChain(),label="Bake Dynamics")
	#Show Main Window Command
	showWindow('dynChainWindow')
	

if __name__ == "__main__":
	main()