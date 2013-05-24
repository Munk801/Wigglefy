#!/usr/bin/env python

"""

@author:
    slu

@description:
    Overlap tool - Rewritten from a basis from the CG Toolkits tool to apply 
    secondary motion.  The tool would be something that we can apply to things 
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
from itertools import izip
import overlap_tool
import maya.cmds as mc
import maya.mel as mm
import pymel
from pymel.all import *

# External
import ani_tools.rmaya.ani_library as ani_lib
from maya_tools.ui.gui_tool_kit import *
from pipe_utils import xml_utils

# UI Stuff
from PyQt4 import QtGui, QtCore
from ui_lib.inputs.button import RButton
from ui_lib.widgets.label import RLabel
from ui_lib.window import RWindow
from ui_lib.layouts.box_layout import RVBoxLayout, RHBoxLayout
from ui_lib.layouts.form_layout import RFormLayout

#---------------------------------------------------------------------------------#
# Globals
#---------------------------------------------------------------------------------#
DYN_STIFFNESS = 0.05
DYN_DAMPING = 0.5
DYN_DRAG = 0
DYN_FRICTION = 0.5
DYN_GRAVITY = 2
DYN_STRENGTH = 0
DYN_FREQUENCY = 0.2
DYN_SPEED = 0.2
DYN_BLEND = 1
DYN_CONTROLLER_SIZE = 5

DYN_SUFFIX = '_DYN'
BLND_SUFFIX = '_BLND'

#---------------------------------------------------------------------------------#
# Helper Functions 
#---------------------------------------------------------------------------------#

def add_dynamic_attributes(jointCtrlObj):
	""" Add all the attributes to the controller.
	Args:
		jointCtrlObj - (str)
			Name of the controller object.
	"""
	addAttr(jointCtrlObj,
	        min=0,ln='stiffness',max=1,keyable=True,at='double',dv=DYN_STIFFNESS)
	#addAttr(jointCtrlObj,
        #        min=0,ln='lengthFlex',max=1,keyable=True,at='double',dv=0)
	addAttr(jointCtrlObj,
                min=0,ln='damping',max=100,keyable=True,at='double',dv=DYN_DAMPING)
	addAttr(jointCtrlObj,
                min=0,ln="drag",max=1,keyable=True,at='double',dv=DYN_DRAG)
	addAttr(jointCtrlObj,
                min=0,ln='friction',max=1,keyable=True,at='double',dv=DYN_FRICTION)
	addAttr(jointCtrlObj,
                min=0,ln="gravity",max=10,keyable=True,at='double',dv=DYN_GRAVITY)
	addAttr(jointCtrlObj,
                min=0,ln="controllerSize",max=100,keyable=True,at='double',dv=DYN_CONTROLLER_SIZE)
	addAttr(jointCtrlObj, ln="turbulenceCtrl", at='bool', keyable=True)
	setAttr((jointCtrlObj + ".turbulenceCtrl"),
                lock=True)
	addAttr(jointCtrlObj,
                min=0,ln="strength",max=1,keyable=True,at='double',dv=DYN_STRENGTH)
	addAttr(jointCtrlObj,
                min=0,ln="frequency",max=2,keyable=True,at='double',dv=DYN_FREQUENCY)
	addAttr(jointCtrlObj,
                min=0,ln="speed",max=2,keyable=True,at='double',dv=DYN_SPEED)
	addAttr(jointCtrlObj,
	        min=0, ln="blend",max=1,keyable=True,at='double',dv=DYN_BLEND)

def add_name_to_attr(jointCtrlObj, obj_names):
	""" Add specified names to the attributes.
	Args:
		jointCtrlObj - (str)
	        	Name of the controller object
	        obj_names - (dict)
	        	Dict with obj as keys and names as values
	"""
	for obj, name in obj_names.iteritems():
		addAttr(jointCtrlObj, ln=name, dt="string", keyable=True)
		setAttr('{ctrl}.{name}'.format(ctrl=jointCtrlObj, name=name), obj, lock=True, type="string")

def build_curve_from_joint(jointPos):
	""" Build the curve from the joint positions.
	Args:
		jointPos - (list)
	        	List of joint positions containing [x,y,z]
	        counter - (int)
	        	Number of joint positions

	"""
	counter = len(jointPos)
	#This string will house the command to create our curve.
	buildCurve="curve -d 1 "
	#Another counter integer for the for loop
	cvCounter=0
	#Loops over and adds the position of each joint to the buildCurve string.
	for i in range(cvCounter, counter):
		buildCurve = "{curve} -p {jpos}".format(
	                curve = buildCurve,
	                jpos = " ".join([str(pos) for pos in jointPos[i]])
	        )
	buildCurve = buildCurve + ";"
	#Adds the end terminator to the build curve command
	#Evaluates the $buildCurve string as a Maya command. (creates the curve running through the joints)
	return str(mel.eval(buildCurve))

def change_visibility(items, visibility):
	""" Change the visiblity of all the items.
	Args:
		items - (list)
			Items to change the visiblity
		visibility - (bool)
			Whether the item should be visible

	"""
	[setAttr("{0}.visibility".format(item), visibility) for item in items]

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

def constrain_joints(joint_names, joint_list, blend_joints):
	constraint_weights = []
	for i, cur_joint in enumerate(joint_list):
		try:
			scaleConstraint(cur_joint, joint_names[i])
			constraint_weights.append(
		                parentConstraint(
		                        cur_joint, 
		                        joint_names[i], 
		                        tl=True, 
		                        mo=True, 
		                        wal=True
		                )
		        )
		except RuntimeError as e:
			warning("Dynamic joints could not constrain to original joints.\n" + e)

	# Create constraints from original joints to the duplicate blend joints	
	for i, cur_joint in enumerate(blend_joints):
		#TEST constrain blend joints to original
		try:
			scaleConstraint(cur_joint, joint_names[i])
			parentConstraint(cur_joint, joint_names[i], mo=True)
		except RuntimeError as e:
			warning("Blended joints could not constrain to original joints.\n" + e)
	return constraint_weights

def create_joints(joint_names, jointPos, joint_list, blend_joints):
	""" Create both the dynamic joint chain and the blend joint chain.  The dynamic joint chain
	will attach to the hair system while the blend joint chain will control the keyed animation.
	
	Args:
		joint_names : (list)
			list of all the joint names
	        jointPos : (list)
			list of x,y,z coordinates of the joints
	        joint_list : (list)
			list to append all the dynamic joints
	        blend_joints : (list)
			list to append all the blend joints
	                
	"""                
	select(deselect=True)
	for i, pos in enumerate(jointPos):
		joint_list.append(
	                joint(
	                        p=(pos[0], pos[1], pos[2]), 
	                        name='{0}{1}'.format(joint_names[i], DYN_SUFFIX)
	                )
	        )

	# Create the blend joints
	select(deselect=True)
	for i, pos in enumerate(jointPos):
		blend_joints.append(
	                joint(
	                        p=(pos[0], pos[1], pos[2]), 
	                        name='{0}{1}'.format(joint_names[i], BLND_SUFFIX)
	                )
	        )
		
def get_joint_info(currentJoint, endJoint, controls):
	joint_names = []
	jointPos = []
	while currentJoint != endJoint:
		joint_names.append(currentJoint)
		jointPos.append(joint(currentJoint, q=1, p=1, a=1))
		pickWalk(d='down')
		sel = ls(selection=True)
		child = sel[0]
		while not isinstance(child, Joint):
			if isinstance(child, Transform) and 'CON' in str(child):
				controls.append(child)
			prev_sel = child
			pickWalk(d='down')
			sel = ls(selection=True)
			# Something doesn't move smoothly down the chain
			if prev_sel == sel[0]:
				children = sel[0].getChildren()
				if not children:
					# We went too far, go back to get the children
					pickWalk(d='up')
					sel = ls(selection=True)
					children = sel[0].getChildren()
				child = [item for item in children if isinstance(item, Joint)][0]
			else:
				child = sel[0]
				
		currentJoint=child
		select(currentJoint)
		sel=mc.ls(selection=True)
	#Theses 3 lines store the position of the end joint that the loop will miss.
	currentJoint=sel[0]
	joint_names.append(currentJoint)
	jointPos.append(joint(currentJoint, q=1,p=1,a=1))
	return joint_names, jointPos

def lock_and_hide_attr(jointCtrlObj):
	""" Lock the attribute and hide it from the menu.
	Args:
		jointCtrlObj - (str)
			Name of the controller object
	"""
	attrs = ['tx', 'ty', 'tz',
	         'rx', 'ry', 'rz',
	         'sx', 'sy', 'sz',]
	for attr in attrs:
		setAttr('{obj}.{attr}'.format(obj = jointCtrlObj, attr = attr), 
	        	lock=True, 
	                keyable=False
		)

def replace_joint_nodes(base_node, all_nodes, blend_joints):
	""" This function will match new controls to the blended joints and delete the old 
	duplicated joints. Take a parent base node, traverse through its entire tree, and replace
	all of its joints with relative blended joints.  Also, hides the blended joints visibility.

	"""
	all_nodes.append(base_node)
	children = base_node.getChildren()
	nodes_to_delete = []
	if not children:
		return all_nodes
	else:
		for child in children:
			if isinstance(child, Joint):
				for joint in blend_joints:
					if str(child) in str(joint):
						nodes_to_delete.append(child)
						parent(joint, base_node)
						setAttr('{0}.visibility'.format(joint), False)
						break
			all_nodes = replace_joint_nodes(child, all_nodes, blend_joints)
	return all_nodes

def set_chain_attr_values(baseJoint):
	""" Set the dynamics chain attrs from GUI values.
	Args:
		baseJoint - (str)
			Name of the base joint which the control is applied to
	                
	"""
	# Set dynamic chain attributes according to creation options
	sliderStiffness=float(floatSliderGrp('sliderStiffness',query=1,value=1))
	sliderDamping=float(floatSliderGrp('sliderDamping',query=1,value=1))
	sliderDrag=float(floatSliderGrp('sliderDrag',query=1,value=1))
	setAttr((baseJoint + "DynChainControl.stiffness"),
                sliderStiffness)
	setAttr((baseJoint + "DynChainControl.damping"),
                sliderDamping)
	setAttr((baseJoint + "DynChainControl.drag"),
                sliderDrag)
	
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

def get_joints_under_controls(control, joint_names, jointPos):
	""" This function will match new controls to the blended joints and delete the old 
	duplicated joints. Take a parent base node, traverse through its entire tree, and replace
	all of its joints with relative blended joints.  Also, hides the blended joints visibility.

	"""
	children = control.getChildren()
	if not children:
		return
	else:
		for child in children:
			if isinstance(child, Joint):
				joint_names.append(child)
				jointPos.append(joint(child, q=1,p=1,a=1))
			else:
				get_joints_under_controls(child, joint_names, jointPos)
	return

#---------------------------------------------------------------------------------#
# Main Functions
#---------------------------------------------------------------------------------#
def create_dynamic_chain():
	""" Create the dynamic joint chains.  Note:  You must have the base controller/joint 
	selected and the end controller/effector shift selected.
	
	"""
	# List of controls
	controls = []	
	
	# Get the selection of controls
	sel = ls(selection=True)
	
	if checkBoxGrp('selectAllControls',q=1,value1=1):
		controls = sel
		#for control in controls:
			#get_joints_under_controls(control, joint_names, jointPos)

	else:
		# There may only be a two joint set or controllers set
		# XXX user should be able to select one controller with 2 joints attached
		try:
			base_ctrl = sel[0]
			end_ctrl = sel[1]
		except IndexError:
			warning("Please select the base and end controllers.")
			return
	
		# Check if joints or controllers are selected
		if not isinstance(base_ctrl, Joint):
			controls.append(base_ctrl)
			base_children = base_ctrl.getChildren()
			baseJoint = [node for node in base_children if isinstance(node, Joint)][0]
		else:
			baseJoint = base_ctrl
	
		if not isinstance(end_ctrl, Joint):	
			end_children = end_ctrl.getChildren()
			endJoint = [node for node in end_children if isinstance(node, Joint)][0]
		else:
			endJoint = end_ctrl

	sel=mc.ls(selection=True)
	#Create a vector array to store the world space coordinates of the joints.
	jointPos=[]
	#Counter integer used in the while loop to determine the proper index in the vector array.
	counter=0
	joint_names = []
	joint_list = []
	jointPos = []
	#Check to ensure proper selection
	if checkBoxGrp('selectAllControls',q=1,value1=1):
		for control in controls:
			get_joints_under_controls(control, joint_names, jointPos)
	#if not ((objectType(baseJoint, isType="joint")) and 
	        #(objectType(endJoint, isType="joint"))):
		#mel.warning("Please select a base and tip joint to make dynamic.")
	else:
		#String variable to house current joint being queried in the while loop.
		currentJoint=baseJoint
		select(baseJoint)
		joint_names, jointPos = get_joint_info(currentJoint, endJoint, controls)
	# Create the list of joints to be parent constrained to the FK joints
	joint_list = []
	blend_joints = []
	create_joints(joint_names, jointPos, joint_list, blend_joints)
	#reset base joint and end joint
	baseJoint = joint_list[0]
	endJoint = joint_list[-1]
	#Now that $jointPos[] holds the world space coords of our joints, 
	#we need to build a cv curve with points at each XYZ coord.
	nameOfCurve = build_curve_from_joint(jointPos)	
	#Make curve dynamic.
	select(nameOfCurve)
	#mel.makeCurvesDynamicHairs()
	mm.eval('makeCurvesDynamicHairs false false true')
	#Determine what the name of the dynamic curve is
	#XXX Need a better way to get the curve name
	nameOfDynCurve=nameOfCurve[5:len(nameOfCurve) + 1]
	dynCurveInstance=str(int(nameOfDynCurve) + 1)
	nameOfDynCurve="curve{0}".format(dynCurveInstance)
	#Create Tip Constraint
	nameOfHairConstraint=[]
	if checkBoxGrp('tipConstraintCheckbox',q=1,value1=1):
		select((nameOfDynCurve + ".cv[" + str(counter) + "]"), r=True)
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
	# Store all the names to the controls as an attr.
	obj_names = {
                nameOfHairSystem : 'nameOfHairShapeNode',
                nameOfFollicle[0] : 'nameOfFollicleNode',
                nameOfDynCurve : 'nameOfDynCurve',
                nameOfUtilityNode : 'nameOfMultiDivNode',
                baseJoint : 'baseJoint',
                endJoint : 'endJoint',
                joint_names[0] : 'linkedBaseJoint',
                joint_names[-1] : 'linkedEndJoint',
        }
	if nameOfHairConstraint:
		obj_names[nameOfHairConstraint[0]] = 'nameOfTipConstraint'
	add_name_to_attr(jointCtrlObj, obj_names)
	
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
	#select(baseJoint,endJoint,nameOfDynCurve)
	select(joint_list[0], joint_list[-1], nameOfDynCurve)
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
	
	# Set dynamic chain attributes according to creation options
	set_chain_attr_values(baseJoint)

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
	
	addAttr(jointCtrlObj, ln='enableDynamics', at='bool')
	# Constrain the dynamic chain to the joint
	constraint_weights = constrain_joints(joint_names, joint_list, blend_joints)

	# For each constraint that was created, link that to a reverse
	reverse_nodes = []
	for p_constraint in constraint_weights:
		reverse_node = createNode('reverse')
		reverse_nodes.append(reverse_node)
		name_base = "_".join(p_constraint.split('_')[:-1])
		in_attr = "{0}.{1}{2}W0".format(str(p_constraint), name_base, DYN_SUFFIX)
		out_attr = "{0}.{1}{2}W1".format(str(p_constraint), name_base, BLND_SUFFIX)
		connectAttr(in_attr, "{0}.inputX".format(str(reverse_node)), f=True)
		connectAttr("{0}.outputX".format(str(reverse_node)), out_attr, f=True)
		connectAttr("{0}.blend".format(jointCtrlObj), in_attr, f=True)
	
	# Duplicate controls and attach to blend joints
	all_nodes = []
	new_control = ''
	if checkBoxGrp('selectAllControls',q=1,value1=1):
		duplicate_controls = [duplicate(control) for control in controls]
		new_control = duplicate_controls[0]
		for dup_ctrl in duplicate_controls:
			all_nodes = replace_joint_nodes(dup_ctrl[0], all_nodes, blend_joints)
	else:	
		new_control = duplicate(controls[0])[0]
		all_nodes = replace_joint_nodes(new_control, all_nodes, blend_joints)
	# Add this to keep track in case of deletion
	add_name_to_attr(jointCtrlObj, {new_control : 'blendControl'})
	
	# Group the Dynamic Chain Control with base control
	parent(baseJoint + "DynChainGroup", controls[0])
	parent(baseJoint, controls[0])
	# Print feedback for user
	displayInfo("Dynamic joint chain successfully setup!\n")
		
#///////////////////////////////////////////////////////////////////////////////////////
#								Collisions Procedure
#///////////////////////////////////////////////////////////////////////////////////////
def collide_with_chain():
	sel=mc.ls(selection=True)
	controllers=[]
	colliders=[]
	#Progress Window Amount
	amount=0
	numberOfObjects=len(sel)
	i=0
	progressWindow(status="Preparing: 0%",
		title="RFX Dynamic Chain Collisions:",
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
			controllers.append(str(obj))
			#Add to controller list
		
		else:
			shapeNode=listRelatives(obj, path = True, s = True)
			#Get the shape node of obj
			#Find current index in collider array
			pos=len(colliders)
			#Check if shape node is a mesh, or a nurbs surface
			if (objectType(shapeNode[0],
				isType="mesh")) or (objectType(shapeNode[0],
				isType="nurbsSurface")):
				colliders.append(str(obj))
				
			
	progressWindow(edit=1,status="Connecting Colliders: 0%")
	numberOfObjects=len(controllers)
	i=0
	#For every controller that was selected...
	for chainCtrl in controllers:
		i+=1
		## Check if the dialog has been cancelled
		#if progressWindow(query=1,isCancelled=1):
			#break
			## Check if end condition has been reached
			
		#if progressWindow(query=1,progress=1)>=100:
			#break
			
		#amount=((100 / numberOfObjects) * i)
		#progressWindow(edit=1,progress=amount)
		#Get the name of the hair shape node
		hairShape=str(getAttr(str(chainCtrl) + ".nameOfHairShapeNode"))
		#For every NURBS or polygon surface that was selected...
		for collider in colliders:
			select(chainCtrl)
			nameofGeoConnector=str(createNode('geoConnector'))
			setAttr((nameofGeoConnector + ".tessellationFactor"), 200)
			#Create geoConnector node and store it's name into a variable
			#Get the shape node of collider
			objShape=listRelatives(collider, path = True, s= True)
			cmd="connectAttr " + str(objShape[0]) + ".message " + nameofGeoConnector+ ".owner;"
			evalEcho(cmd)
			cmd="connectAttr " + str(objShape[0]) + ".worldMatrix[0] " + nameofGeoConnector+ ".worldMatrix;"
			evalEcho(cmd)
			cmd="connectAttr " + str(objShape[0]) + ".outMesh " + nameofGeoConnector+ ".localGeometry;"
			evalEcho(cmd)
			cmd="connectAttr -na " + nameofGeoConnector+ ".resilience " + str(hairShape) + ".collisionResilience;"
			evalEcho(cmd)
			cmd="connectAttr -na " + nameofGeoConnector+ ".friction " + str(hairShape) + ".collisionFriction;"
			evalEcho(cmd)
			cmd="connectAttr -na " + nameofGeoConnector+ ".sweptGeometry " + str(hairShape) + ".collisionGeometry;"
			evalEcho(cmd)
			cmd="connectAttr time1.outTime " + nameofGeoConnector+ ".currentTime"
			evalEcho(cmd)			
			#Connect all the necessary attributes to make the surface collide
			#connectAttr((objShape[0] + ".message"),(nameofGeoConnector + ".owner"))
			#connectAttr((objShape[0] + ".worldMatrix[0]"),(nameofGeoConnector + ".worldMatrix"))
			#connectAttr((objShape[0] + ".outMesh"),(nameofGeoConnector + ".localGeometry"))
			#connectAttr((hairShape + ".collisionResilience"),
				#(nameofGeoConnector + ".resilience"), na=True, f=True)
			#connectAttr((hairShape + ".collisionFriction"),
				#(nameofGeoConnector + ".friction"), na=True, f=True)
			#connectAttr((hairShape + ".collisionGeometry"),
				#(nameofGeoConnector + ".sweptGeometry"), na=True, f=True)
			#connectAttr('time1.outTime',(nameofGeoConnector + ".currentTime"))
			#connectAttr((nameofGeoConnector + ".owner"), (objShape[0] + ".message"), f=True, na=True)
			#connectAttr((nameofGeoConnector + ".worldMatrix"), (objShape[0] + ".worldMatrix[0]"), f=True, na=True)
			#connectAttr((nameofGeoConnector + ".localGeometry"), (objShape[0] + ".outMesh"), f=True, na=True)
			#connectAttr((nameofGeoConnector + ".resilience"), 
			            #(hairShape + ".collisionResilience"), f=True,  na = True)
			
			#connectAttr((nameofGeoConnector + ".friction"), 
			            #(hairShape + ".collisionFriction"), f=True, na = True)
			#connectAttr((nameofGeoConnector + ".sweptGeometry"), 
			            #(hairShape + ".collisionGeometry"), f = True, na = True)
			#connectAttr((nameofGeoConnector + ".currentTime"), 'time1.outTime', f = True, na=True)
			#Print output to the user for each connected collider.
			print str(obj) + " has been set to collide with " + str(chainCtrl) + "\n"
			
	progressWindow(endProgress = True)
	

#///////////////////////////////////////////////////////////////////////////////////////
#								BAKING PROCEDURE
#///////////////////////////////////////////////////////////////////////////////////////
def bake_dynamic_chain():
	initialSel=mc.ls(selection=True)
	#Declare necessary variables
	allCtrls=[]
	i=0
	amount=0
	#Filter selection to contain only dynamic chain controllers.
	for obj in initialSel:
		if mel.attributeExists("nameOfHairShapeNode", obj):
			allCtrls.append(str(obj))
			i += 1
		
	progressWindow(
	        status="Baking Joint Chains:",
		title="RFX Dynamic Joint Chain:",
		maxValue=100,
		minValue=0,
		isInterruptable=True,
		progress=amount
	)
	#Create a progress window
	#Construct frame range variable
	frameRangeToBake=''
	startFrame=float(intField('startFrame',query=1,value=1))
	endFrame=float(intField('endFrame',query=1,value=1))
	frameRangeToBake = '"{sf}:{ef}"'.format(sf = str(startFrame), ef = str(endFrame))
	j=1
	#For all of the selected chain controllers.
	for obj in allCtrls:
		if progressWindow(query=1, isCancelled=1):
			break
			# Check if the dialog has been cancelled
			# Check if end condition has been reached
			
		if progressWindow(query=1, progress=1) >= 100:
			break
			
		amount=((100 / i) * j)
		progressWindow(edit=1,progress=amount)
		progressWindow(edit=1,status=("Baking chain " + str(j) + " of " + str(i) + " :"))
		j+=1
		chainCtrl = str(obj)
		baseJoint = str(getAttr(chainCtrl + ".baseJoint"))
		endJoint = str(getAttr(chainCtrl + ".endJoint"))
		bakingJoints = "{\""
		currentJoint = [endJoint]
		#Determine joints to be baked
		while currentJoint[0] != baseJoint:
			bakingJoints=(bakingJoints + currentJoint[0] + "\", \"")
			select(currentJoint[0])
			currentJoint=pickWalk(d='up')
			
		
		bakingJoints=(bakingJoints + baseJoint + "\"}")
		#Add the base joint that the while loop will miss
		#Concatenate the bake simulation command with the necessary joint names.
		bakingJoints=(
		        "bakeResults -simulation true -t " + frameRangeToBake + \
		        " -sampleBy 1 -disableImplicitControl true -preserveOutsideKeys true"\
		        " -sparseAnimCurveBake false -controlPoints false -shape true" + bakingJoints
		)
		#Evaluate the $bakingJoints string to bake the simulation.
		mel.eval(bakingJoints)
		#Tell control object that joints are baked.
		setAttr((chainCtrl + ".bakingState"),
			1)
		#Print feedback to user
		print "All joints controlled by " + chainCtrl + " have now been baked!\n"
		
	progressWindow(endProgress = True)
	

#///////////////////////////////////////////////////////////////////////////////////////
#								DELETE DYNAMICS PROCEDURE
#///////////////////////////////////////////////////////////////////////////////////////
def delete_dynamic_chain():
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
		#Delete Hair System Node
		hairSystemName = str(getAttr(chainCtrl + ".nameOfHairShapeNode"))
		select(hairSystemName)
		hairSystemName=pickWalk(d='up')
		delete(hairSystemName)
		#Delete Follicle Node
		follicleNode = str(getAttr(chainCtrl + ".nameOfFollicleNode"))
		select(follicleNode)
		follicleNode=pickWalk(d='up')
		delete(follicleNode)
		#Delete Dynamic Hair Curve
		delete(getAttr(chainCtrl + ".nameOfDynCurve"))
		#Delete Tip Constraint
		try:
			delete(getAttr(chainCtrl + ".nameOfTipConstraint"))
		except pymel.core.general.MayaAttributeError, pymel.core.general.MayaNodeError:
			pass
		try:
			delete(getAttr(chainCtrl + ".nameOfMultiDivNode"))
		except Exception:
			pass
		
		# Delete the IK Handle attached
		baseJoint=str(getAttr(chainCtrl + ".baseJoint"))
		delete(baseJoint + "ikHandle")
		
		# Delete the dynamic joints involved	
		delete(baseJoint)
		
		# Delete blend joints and controls	
		blend_controls = str(getAttr(chainCtrl + ".blendControl"))
		delete(blend_controls)
		
		#Delete control object
		select(chainCtrl)
		group = pickWalk(d='up')
		delete(group)
		
		#Print feedback to the user.
		print "Dynamics have been deleted from the chain.\n"
		

def disable_dynamics():
	sel=mc.ls(selection=True)
	try:
		dyn_ctrl = sel[0]
	except IndexError:
		mel.warning("Please select the dyamic controller.")
	# Get all the children of the dag node
	dag_node = DagNode(pickWalk(d='up')[0])
	dag_children = dag_node.getChildren()
	ik_handle = ''
	for child in dag_children:
		if isinstance(child, IkHandle):
			ik_handle = child	
	try:	
		ik_handle.disableHandles()
	except AttributeError:
		mel.warning("Cannot find IK handle attached to controller group")
	
def enable_dynamics():
	sel=mc.ls(selection=True)
	try:
		dyn_ctrl = sel[0]
	except IndexError:
		mel.warning("Please select the dynamic controller.")
	# Get all the children of the dag node
	dag_node = DagNode(pickWalk(d='up')[0])
	dag_children = dag_node.getChildren()
	ik_handle = ''
	for child in dag_children:
		if isinstance(child, IkHandle):
			ik_handle = child	
	try:	
		ik_handle.enableHandles()
	except AttributeError:
		mel.warning("Cannot find IK handle attached to controller group")

def create_character_from_prefs():
	# XXX Doesn't do any error checking for names in xml file
	# XXX Only does joints.  What about attrs?
	item = fileDialog()
	prefs = xml_utils.ElementTree.parse(str(item))
	root = prefs.getroot()
	for child in root:
		if child.tag == 'joints':
			for joint in child.getchildren():
				base_joint = joint.attrib['base']
				end_joint = joint.attrib['end']
				select([base_joint, end_joint], replace=True)
				create_dynamic_chain()
	for child in root:
		if child.tag =='attrs':
			for attr in child.getchildren():
				for setting, value in attr.attrib.iteritems():
					if setting == 'name':
						continue
					setAttr(
					        '{0}.{1}'.format(attr.attrib['name'], setting), 
					        float(value)
					)



def save_character_to_prefs():
	# XXX Currently expects selection to go "base, end, base, end, etc"
	# XXX Overrides current xml file.  Maybe it doesn't need to do that
	
	item = fileDialog2()
	all_ctrls = ls(selection=True)
	root = xml_utils.ElementTree.Element('data')
	joints = xml_utils.ElementTree.SubElement(root, 'joints')
	attrs = xml_utils.ElementTree.SubElement(root, 'attrs')
	# Save the joints
	for ctrl in all_ctrls:
		base_joint = getAttr('{0}.linkedBaseJoint'.format(ctrl))
		end_joint = getAttr('{0}.linkedEndJoint'.format(ctrl))
		joint_info = xml_utils.ElementTree.SubElement(joints, 'joint')
		joint_info.set('base', base_joint)
		joint_info.set('end', end_joint)
		joint_info.set('name', ctrl)
		
		# Save the attrs
		attr_info = xml_utils.ElementTree.SubElement(attrs, 'attr')
		attr_dict = {
			'stiffness' : getAttr('{0}.stiffness'.format(ctrl)),
			'damping' : getAttr('{0}.damping'.format(ctrl)),
			'drag' : getAttr('{0}.drag'.format(ctrl)),
			'friction' : getAttr('{0}.friction'.format(ctrl)),
			'gravity' : getAttr('{0}.gravity'.format(ctrl)),
			'controllerSize' : getAttr('{0}.controllerSize'.format(ctrl)),
			'strength' : getAttr('{0}.strength'.format(ctrl)),
			'frequency' : getAttr('{0}.frequency'.format(ctrl)),
			'speed' : getAttr('{0}.speed'.format(ctrl)),
			'blend' : getAttr('{0}.blend'.format(ctrl))
		}
		attr_info.set('name', ctrl)
		for attr_name, attr_val in attr_dict.iteritems():
			attr_info.set(attr_name, str(attr_val))
	xml_utils.indent(root)
	tree = xml_utils.ElementTree.ElementTree(root)
	tree.write(str(item[0]))

def pairwise(iterable):
	a = iter(iterable)
	return izip(a, a)

#///////////////////////////////////////////////////////////////////////////////////////
#								MAIN WINDOW
#///////////////////////////////////////////////////////////////////////////////////////
def main():
	#XXX TODO: Switch from using MELs gui system to ui_lib
	if window('dynChainWindow',q=1,ex=1):
		deleteUI('dynChainWindow')
		#Main Window
		
	window('dynChainWindow',h=200,w=360,title="RFX Overlapping Tool")
	scrollLayout(hst=0)
	columnLayout('dynChainColumn')
	#Dynamic Chain Creation Options Layout
	frameLayout('creationOptions',h=150,
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
	checkBoxGrp('selectAllControls', cw=(1, 150), label = "Run on All Selected Controls ")
	#separator -h 20  -w 330;
	setParent('..')
	setParent('..')
	#Button Layouts
	rowColumnLayout(nc=2,cw=[(1, 175), (2, 150)])
	text("Select base joint, shift select tip: ")
	button(c=lambda *args: overlap_tool.create_dynamic_chain(),label="Make Dynamic")
	text("Select all ctrls and colliders: ")
	button(c=lambda *args: overlap_tool.collide_with_chain(),label="Make Collide")
	text("Select control: ")
	button(c=lambda *args: overlap_tool.delete_dynamic_chain(),label="Delete Dynamics")
	text("Disable Dynamics: ")
	button(c=lambda *args: overlap_tool.disable_dynamics(), label="Disable Dynamics")
	text("Enable Dynamics: ")
	button(c=lambda *args: overlap_tool.enable_dynamics(), label="Enable Dynamics")
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
	button(c=lambda *args: overlap_tool.bake_dynamic_chain(),label="Bake Dynamics")
	
	# XXX TODO Add section for opening prefs files.
	setParent('..')
	separator(h=20, w=330)
	text("                               -Character Prefs-")
	rowColumnLayout('prefsRowColumn',nc=2, cw=[(1, 175), (2, 150)])
	text("Open Character Prefs: ")
	button(c=lambda *args: overlap_tool.create_character_from_prefs(), label="Open Character Prefs")
	text("Select joints by base->end")
	button(c=lambda *args: overlap_tool.save_character_to_prefs(), label="Save Character Prefs")
	#Show Main Window Command
	showWindow('dynChainWindow')
	
class OverlapTool(RWindow):
	def __init__(self):
		super(OverlapTool, self).__init__()
		self.initUI()
		
	def initUI(self):
		pass

if __name__ == "__main__":
	main()