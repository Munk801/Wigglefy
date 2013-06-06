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
from pymel.core.runtime import ClusterCurve

# External
import ani_tools.rmaya.ani_library as ani_lib
from maya_tools.ui.gui_tool_kit import *
from pipe_utils import xml_utils

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
MAGNETISM = 1

DYN_SUFFIX = '_DYN'
BLND_SUFFIX = '_BLND'

ITERATIONS = 10

USING_ALL_CONTROLS = False
HAS_TIP_CONSTRAINT = False
ALLOW_CHAIN_STRETCH = False


#---------------------------------------------------------------------------------#
# Helper Functions 
#---------------------------------------------------------------------------------#
def add_duplicate_blend_controls(jointCtrlObj, controls, blend_joints):
	# Duplicate controls and attach to blend joints
	select(deselect=True)
	all_nodes = []
	new_control = ''
	#new_ctrl_group = group(name='{0}_BlendCtrlGroup'.format(str(jointCtrlObj)))
	# If select all controls is checked, then we need every control.  Whereas if it is,
	# not checked, we can assume that the controls are in a hierarchy structure.  Thus,
	# getting the first control will grab the hierarchy for the entire control set
	if USING_ALL_CONTROLS: 
		duplicate_controls = [duplicate(str(control)) for control in controls]
		new_control = duplicate_controls[0][0]
		for dup_ctrl in duplicate_controls:
			all_nodes = replace_joint_nodes(dup_ctrl[0], all_nodes, blend_joints)
			#parent(dup_ctrl, new_ctrl_group)
	else:	
		first_control = str(controls[0])
		new_control = duplicate(first_control, renameChildren=True)[0]
		all_nodes = replace_joint_nodes(new_control, all_nodes, blend_joints)
		#parent(new_control, new_ctrl_group)
	# Add this to keep track in case of deletion
	add_name_to_attr(jointCtrlObj, {'blendControl' : new_control})
	#parent(new_control, world=True)
	
	# Turn off visibility on new controls
	addAttr(jointCtrlObj, ln="blendCtrlVis", at='bool', keyable=True)
	#connectAttr('{0}.blendCtrlVis'.format(jointCtrlObj),'{0}.visibility'.format(new_ctrl_group)) 
	#try:
		#setAttr("{0}.visibility".format(new_control), 0)
	#except RuntimeError as e:
		#displayInfo("Cannot set visibility for {0}".format(new_control))
	return all_nodes

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
	        min = 0, ln = 'iterations', max = 10000, keyable = True, at='double', dv=ITERATIONS)
	addAttr(jointCtrlObj,
                min=0,ln='damping',max=100,keyable=True,at='double',dv=DYN_DAMPING)
	addAttr(jointCtrlObj,
                min=0,ln="drag",max=1,keyable=True,at='double',dv=DYN_DRAG)
	addAttr(jointCtrlObj,
                min=0,ln='friction',max=1,keyable=True,at='double',dv=DYN_FRICTION)
	addAttr(jointCtrlObj,
                min=0,ln="gravity",max=10,keyable=True,at='double',dv=DYN_GRAVITY)
	addAttr(jointCtrlObj,
                min=0,ln="controllerSize",max=500,keyable=True,at='double',dv=DYN_CONTROLLER_SIZE)
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
	addAttr(jointCtrlObj,
	        min=0, ln="magnetism", max=1, keyable=True, at='double', dv=MAGNETISM)

def add_name_to_attr(jointCtrlObj, obj_names):
	""" Add specified names to the attributes.
	Args:
		jointCtrlObj - (str)
	        	Name of the controller object
	        obj_names - (dict)
	        	Dict with obj as keys and names as values
	"""
	for name, obj in obj_names.iteritems():
		addAttr(jointCtrlObj, ln=name, dt="string", keyable=True)
		setAttr('{ctrl}.{name}'.format(ctrl=jointCtrlObj, name=name), obj, lock=True, type="string")

def build_clusters_from_curve(nameOfCurve, numJoints):
	select(nameOfCurve)
	ClusterCurve()
	last_cluster = ls(selection=True)[0]
	last_num = int(str(last_cluster).lstrip('cluster').rstrip('Handle'))
	clusters = ["cluster{0}Handle".format(i) for i in range(last_num - numJoints + 1, last_num + 1)]
	# Hide all the clusters
	change_visibility(clusters, 0)
	return clusters


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

def constrain_joints(joint_names, joint_list, blend_joints, joints_per_control):
	""" Constrains the original joints to the dynamic joints and
	the blended joints.  Does a parent and scale constrain to the original joints
	Args:
		joint_names : (list)
			List of joint names
	        joint_list : (list)
			List of dynamic joints
	        blend_joints : (list)
			List of blend joints
	        
	"""
	constraint_weights = []
	# In the instance that there are more controls than joints, use the same controller
	constrainer = []
	if len(joint_names) < len(joint_list):
		for i, num_joints in enumerate(joints_per_control):
			for joint_instance in range(num_joints):
				constrainer.append(joint_names[i])
	else:
		constrainer = joint_names
	#constrainer.append(joint_names[-1])
	for i, cur_joint in enumerate(joint_list):
		try:
			scaleConstraint(cur_joint, constrainer[i])
		except RuntimeError as e:
			displayInfo("Unable to perform scale constrain on {0}".format(constrainer[i]))
		try:
			constraint_weights.append(
		                parentConstraint(
		                        cur_joint, 
		                        constrainer[i], 
		                        tl=True, 
		                        mo=True, 
		                        wal=True
		                )
		        )
		except RuntimeError as e:
			displayInfo("Dynamic joints could not constrain to original joints.\n" )

	# Create constraints from original joints to the duplicate blend joints	
	for i, cur_joint in enumerate(blend_joints):
		try:
			scaleConstraint(cur_joint, constrainer[i])
		except RuntimeError as e:
			displayInfo("Unable to perform scale constrain on {0}".format(constrainer[i]))
		try:
			parentConstraint(cur_joint, constrainer[i], mo=True)
		except RuntimeError as e:
			displayInfo("Blended joints could not constrain to original joints.\n")
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
	# Get the instance number of each joint.  Some joints may have different instance numbers
	joint_instances = [
	        get_instance_number(
	                prefix="{0}_".format(joint_name), 
	                suffix=DYN_SUFFIX
	        ) for joint_name in joint_names
	]
	for i, pos in enumerate(jointPos):
		joint_list.append(
	                joint(
	                        p=(pos[0], pos[1], pos[2]), 
	                        name='{0}_{1}{2}'.format(joint_names[i], joint_instances[i], DYN_SUFFIX)
	                )
	        )

	# Create the blend joints
	select(deselect=True)
	joint_instances = [
	        get_instance_number(
	                prefix="{0}_".format(joint_name), 
	                suffix=BLND_SUFFIX
	        ) for joint_name in joint_names
	]
	for i, pos in enumerate(jointPos):
		blend_joints.append(
	                joint(
	                        p=(pos[0], pos[1], pos[2]), 
	                        name='{0}_{1}{2}'.format(joint_names[i], joint_instances[i], BLND_SUFFIX)
	                )
	        )
		
def get_joint_info(currentJoint, endJoint, controls):
	""" Uses the base joint and the end joint to gather all
	the joint names and joint positions.  Will also append
	any controllers to the given list. 
	Args:
		currentJoint : (str)
			The base joint to start from
	        endJoint : (str)
			The end effector joint
	        controls : (list)
			The list that you want to append any controls to
	Returns:
		(joint_names, jointPos)
			Returns both a list of the joint names and the joint positions.
	
	"""
	joint_names = []
	jointPos = []
	joints_per_control = [0]
	count = 0;
	while currentJoint != endJoint:
		joint_names.append(currentJoint)
		jointPos.append(joint(currentJoint, q=1, p=1, a=1))
		joints_per_control[count] += 1
		pickWalk(d='down')
		sel = ls(selection=True)
		child = sel[0]
		while not isinstance(child, Joint):
			if isinstance(child, Transform) and 'CON' in str(child):
				controls.append(child)
				count += 1
				joints_per_control.append(0)
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
	return joint_names, jointPos, joints_per_control

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

def set_chain_attr_values(jointCtrlObj):
	""" Set the dynamics chain attrs from GUI values.
	Args:
		baseJoint - (str)
			Name of the base joint which the control is applied to
	                
	"""
	# Set dynamic chain attributes according to creation options
	sliderStiffness=float(floatSliderGrp('sliderStiffness',query=1,value=1))
	sliderDamping=float(floatSliderGrp('sliderDamping',query=1,value=1))
	sliderDrag=float(floatSliderGrp('sliderDrag',query=1,value=1))
	setAttr((jointCtrlObj + ".stiffness"),
                sliderStiffness)
	setAttr((jointCtrlObj + ".damping"),
                sliderDamping)
	setAttr((jointCtrlObj + ".drag"),
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

def find_end_joint(start_control, end_joint= '', to_next_control=False):
	""" Find an end joint given a start controller position. This will
	continue down the chain to find the last joint.  If to_next_control
	is set to True,  it will stop at the next available controller.
	
	"""
	children = start_control.getChildren()
	if not children:
		return end_joint
	else:
		for child in children:
			# Go until the next controller is found.
			if to_next_control and str(child).endswith('CON'):
				return end_joint
			if isinstance(child, Joint) and 'END' not in str(child):
				end_joint = child
				end_joint = find_end_joint(child, end_joint, to_next_control)
			else:
				end_joint = find_end_joint(child, end_joint, to_next_control)
	return end_joint

def get_instance_number(prefix='', instance=0, suffix=''):
	while objExists("{0}{1}{2}".format(prefix, instance, suffix)):
		instance += 1
	return instance

#---------------------------------------------------------------------------------#
# Main Functions
#---------------------------------------------------------------------------------#
def create_dynamic_chain():
	""" Create the dynamic joint chains.  Note:  You must have the base controller/joint 
	selected and the end controller/effector shift selected.
	
	"""
	global USING_ALL_CONTROLS
	# List of controls
	controls = []
	# Joint Control connections
	control_mapper = {}
	# Get the selection of controls
	sel = ls(selection=True)
	# Nothing was selected	
	if len(sel) == 0:
		warning("No controllers selected.  Please select controllers to create a chain.")
		return
	# Non-hierarchy controls were selected.  Process each of them individually
	elif len(sel) > 2:
		USING_ALL_CONTROLS = True
		controls = sel
	# Only one control was selected.  Check if that has two joints to create a chain
	elif len(sel) == 1:
		if not isinstance(sel[0], Joint):
			controls.append(sel[0])
			baseJoint = [item for item in sel[0].getChildren() if isinstance(item, Joint)][0]
			endJoint = find_end_joint(sel[0], to_next_control=True)
			if endJoint == '':
				warning("Only one controller selected with one joint attached.")
				return
		else:
			warning("Only a single joint selected.  Need a base joint and end joint.")
			return
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
			endJoint = find_end_joint(end_ctrl, to_next_control=True)
			#end_children = end_ctrl.getChildren()
			#endJoint = [node for node in end_children if isinstance(node, Joint)][0]
		else:
			endJoint = end_ctrl

	sel = mc.ls(selection=True)
	# Create a vector array to store the world space coordinates of the joints.
	jointPos = []
	# Counter integer used in the while loop to determine the proper index in the vector array.
	counter = 0
	# List of the dynamic joints the joint names
	joint_names = []
	# List of the dynamic joints
	joint_list = []
	# List of all the joint positions in as [x,y,z]	
	jointPos = []
	# In conjunction with the controls list, will state how many joints are set per control
	joints_per_control = []
	#Check to ensure proper selection
	if USING_ALL_CONTROLS: 
		for control in controls:
			get_joints_under_controls(control, joint_names, jointPos)
		joints_per_control = [1 for control in controls]
	else:
		#String variable to house current joint being queried in the while loop.
		currentJoint=baseJoint
		select(baseJoint)
		joint_names, jointPos, joints_per_control = get_joint_info(currentJoint, endJoint, controls)
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
	select(joint_list[0], joint_list[-1])
	ik_info = ikHandle(ccv=True,sol='ikSplineSolver',simplifyCurve=True)
	curve = ik_info[-1]
	select(curve)
	mm.eval('dynCreateSoft 0 0 1 1 0')
	constraint_weights = constrain_joints(
	        controls, 
	        joint_list, 
	        blend_joints, 
	        joints_per_control
	)
	#mm.eval('makeCurvesDynamicHairs false false true')
	##Determine what the name of the dynamic curve is
	##XXX Need a better way to get the curve name
	#nameOfDynCurve=nameOfCurve[5:len(nameOfCurve) + 1]
	#dynCurveInstance=str(int(nameOfDynCurve) + 1)
	#nameOfDynCurve="curve{0}".format(dynCurveInstance)
	##Create Tip Constraint
	#nameOfHairConstraint=[]
	#if checkBoxGrp('tipConstraintCheckbox',q=1,value1=1):
		#select((nameOfDynCurve + ".cv[" + str(counter) + "]"), r=True)
		#mel.createHairConstraint(0)
		#selection=pickWalk(d='up')
		#nameOfHairConstraint.append(selection[0])
		#nameOfHairConstraint[0]=str(rename(nameOfHairConstraint[0],
	                #(baseJoint + "TipConstraint")))
		
	#curveInfoNode=''
	##Make Joint Chain Stretchy
	#nameOfUtilityNode=''
	#if checkBoxGrp('stretchCheckbox',q=1,value1=1):
		#stretch_chain(nameOfDynCurve, baseJoint, endJoint)
		
	#select(nameOfDynCurve)
	##Display Current Position of Hair
	#mel.displayHairCurves("current", 1)
	##Determine name of follicle node
	#select(nameOfCurve)
	#nameOfFollicle=pickWalk(d='up')
	##Create Joint Chain Controller Object
	#jointCtrlObjArray=[]
	#jointCtrlObjArray.append(str(createNode('implicitSphere')))
	#jointCtrlObjArray=pickWalk(d='up')
	#jointCtrlObj=jointCtrlObjArray[0]
	##Point Constrain Control Object to the end joint
	#pointConstraint(endJoint,jointCtrlObj)
	##Add attributes to controller for the dynamics
	#add_dynamic_attributes(jointCtrlObj)
	
	##Determine what the name of the hair system is
	#nameOfHairSystem=''
	#sizeOfString=len(nameOfFollicle[0])
	#sizeOfString+=1
	#nameOfHairSystem=nameOfFollicle[0][8:sizeOfString]
	#sizeOfString=int(nameOfHairSystem)
	#nameOfHairSystem=("hairSystemShape" + str(sizeOfString))
	## Store all the names to the controls as an attr.
	#obj_names = {
	        #'nameOfHairShapeNode' : nameOfHairSystem,
	        #'nameOfFollicleNode' : nameOfFollicle[0],
	        #'nameOfDynCurve' : nameOfDynCurve,
	        #'nameOfMultiDivNode' : nameOfUtilityNode,
	        #'baseJoint' : baseJoint,
	        #'endJoint' : endJoint,
	        #'linkedBaseJoint' : joint_names[0],
	        #'linkedEndJoint' : joint_names[-1],
	        #'baseControl' : controls[0],
	        #'endControl' : controls[-1],
	        #'allControls' : ','.join([str(control) for control in controls]),
	        #'allDynJoints' : ','.join([str(joint) for joint in joint_list]),
	#}
	#if nameOfHairConstraint:
		#obj_names['nameOfTipConstraint'] = nameOfHairConstraint[0]
	#add_name_to_attr(jointCtrlObj, obj_names)
	
	##Add special attribute to house baking state
	#addAttr(jointCtrlObj, ln='bakingState', at='bool')
	##Add special attribute to house stretchy state
	#addAttr(jointCtrlObj, ln='isStretchy', at='bool')
	##Add attribute to house if all controls needed to create dynamics
	#addAttr(jointCtrlObj, ln='usesAllControls', at='bool')	
	#if checkBoxGrp('stretchCheckbox',q=1,value1=1):
		#setAttr((jointCtrlObj + ".isStretchy"), 1)
	
	#if USING_ALL_CONTROLS: 
		#setAttr((jointCtrlObj + ".usesAllControls"), 1)

	##Overide the Hair dynamics so that the follicle controls the curve dynamics
	#select(nameOfFollicle)
	#nameOfFollicle=pickWalk(d='down')
	#setAttr((nameOfFollicle[0] + ".overrideDynamics"), 1)
	
	##Set the dynamic chain to hang from the base joint (not both ends)
	#setAttr((nameOfFollicle[0] + ".pointLock"), 1)
	 
	##Connect attributes on the controller sphere to the follicle node
	#ctrl_to_follicle_attrs = {
                #'stiffness' : 'stiffness',
                #'damping' : 'damp',
	        #'magnetism' : 'startCurveAttract',
        #}
	#connect_controller_to_system(jointCtrlObj, nameOfFollicle[0], ctrl_to_follicle_attrs)

	##Connect attribute on the controller sphere to the hair system node
	#ctrl_to_hairsystem_attrs = {
                #'drag' : 'drag',
                #'friction' : 'friction',
                #'gravity' : 'gravity',
                #'strength' : 'turbulenceStrength',
                #'frequency' : 'turbulenceFrequency',
                #'speed' : 'turbulenceSpeed',
	        #'iterations' : 'iterations',
        #}
	#connect_controller_to_system(jointCtrlObj, nameOfHairSystem, ctrl_to_hairsystem_attrs)
	
	##Connect scale of controller to the size attr
	#connectAttr((jointCtrlObj + ".controllerSize"),
                    #(jointCtrlObj + ".scaleX"), f=True)
	#connectAttr((jointCtrlObj + ".controllerSize"), 
                    #(jointCtrlObj + ".scaleY"), f=True)
	#connectAttr((jointCtrlObj + ".controllerSize"), 
                    #(jointCtrlObj + ".scaleZ"), f=True)
	
	##Lock And Hide Attributes on Control Object.
	#lock_and_hide_attr(jointCtrlObj)
	
	## Get the instance of the ikHandle
	#ik_instance = get_instance_number("{0}ikHandle".format(baseJoint))

	##Build the splineIK handle using the dynamic curve.
	##select(baseJoint,endJoint,nameOfDynCurve)
	#select(joint_list[0], joint_list[-1], nameOfDynCurve)
	#nameOfIKHandle=ikHandle(ccv=False,sol='ikSplineSolver')
	#nameOfIKHandle[0]=str(rename(nameOfIKHandle[0],
                #(baseJoint + "ikHandle{0}".format(ik_instance))))

	##Rename Ctrl Obj
	#jointCtrlObj=str(rename(jointCtrlObj, (baseJoint + "DynChainControl")))
	##Parent follicle node to the parent of the base joint
	##This will attach the joint chain to the rest of the heirarchy if there is one.
	#select(nameOfFollicle[0])
	#pickWalk(d='up')
	#follicleGrpNode=pickWalk(d='up')
	#follicleGrpNode = rename(follicleGrpNode, "{0}_FollicleSystem".format(baseJoint))
	#add_name_to_attr(jointCtrlObj, {'nameOfFollicleSystem' : follicleGrpNode})
	##Determine parent of base joint
	#select(baseJoint)
	#parentOfBaseJoint=pickWalk(d='up')
	#if parentOfBaseJoint[0] == baseJoint:
		#mel.warning("No parent hierarchy was found for the dynamic chain.\n")
	#else:
		#parent(follicleGrpNode,parentOfBaseJoint)
		## Parent the follicle into heirarchy
		#parent(nameOfDynCurve, w=True)
	
	## Set dynamic chain attributes according to creation options
	#set_chain_attr_values(jointCtrlObj)

	## Group the dynamic chain nodes
	#nameOfGroup=str(group(jointCtrlObj,nameOfDynCurve,nameOfIKHandle[0],nameOfHairSystem,
                #name=(baseJoint + "DynChainGroup")))
	## If the chain has a tip constraint, then parent this under the main group
	#if checkBoxGrp('tipConstraintCheckbox',q=1,value1=1):
		#parent(nameOfHairConstraint[0],nameOfGroup)
		
	## Turn the visibility of everything off to reduce viewport clutter.
	#items_to_hide = [
                #nameOfDynCurve,
                #nameOfIKHandle[0],
                #follicleGrpNode,
                #nameOfHairSystem,
        #]
	#change_visibility(items_to_hide, visibility=False)
		
	## Delete useless 'hairsystemoutputcurves' group node
	#select(nameOfHairSystem)
	#nameOfGarbageGrp=pickWalk(d='up')
	#delete(nameOfGarbageGrp[0] + "OutputCurves")
	## Select dynamic chain controller for user
	#select(str(jointCtrlObj))
	
	#addAttr(jointCtrlObj, ln='enableDynamics', at='bool')
	## Constrain the dynamic chain to the joint
	#constraint_weights = constrain_joints(
	        #controls, 
	        #joint_list, 
	        #blend_joints, 
	        #joints_per_control
	#)

	## For each constraint that was created, link that to a reverse
	#reverse_nodes = []
	#for i,p_constraint in enumerate(constraint_weights):
		#reverse_node = createNode('reverse')
		#reverse_nodes.append(reverse_node)
		#attr_list = p_constraint.listAttr()
		#in_attr = [attr for attr in attr_list if '{0}W'.format(DYN_SUFFIX) in str(attr)]
		#out_attr = [attr for attr in attr_list if '{0}W'.format(BLND_SUFFIX) in str(attr)]
		## Set up the reverse node to take the dynamic attr for the input and 
		## blend attr for the output
		#for j, attr in enumerate(in_attr):
			#connectAttr(in_attr[j], "{0}.inputX".format(str(reverse_node)), f=True)
			#connectAttr("{0}.outputX".format(str(reverse_node)), out_attr[j], f=True)
			#blendname = "blend{0}".format(i)
			#addAttr(jointCtrlObj, 
			        #min=0, ln=blendname,max=1,keyable=True,at='double',dv=1.0)
			#connectAttr("{0}.blend{1}".format(jointCtrlObj, i), in_attr[j], f=True)

	#dupe_nodes = add_duplicate_blend_controls(jointCtrlObj, controls, blend_joints)
	#dupe_controls = []
	#for node in dupe_nodes:
		#if len(dupe_controls) < len(controls) and str(node).endswith('CON'):
			#dupe_controls.append(node)

	## Build Clusters from curve
	#clusters = build_clusters_from_curve(nameOfDynCurve, len(jointPos))
	
	## Constrain the clusters to the duplicate controls
	#for i, dupe_control in enumerate(dupe_controls):
		#scaleConstraint(dupe_control, clusters[i])
		#parentConstraint(dupe_control, clusters[i])
	#select(deselect=True)
	## Create a new group
	#dynamic_group = group(name='{0}_DynamicChainGroup'.format(baseJoint))
	## Parent all the controls to new group
	#parent(blend_joints[0], follicleGrpNode)
	#parent(joint_list[0], follicleGrpNode)
	#parent(baseJoint + "DynChainGroup", dynamic_group)
	##parent(dynamic_group, controls[0].getParent())
	#parent(follicleGrpNode, controls[0].root())
	##parent(clusters, follicleGrpNode)
	
	## Hide original controllers visiblity
	##change_visibility(controls, 0)
	
	## Print feedback for user
	#select(jointCtrlObj)
	
	#USING_ALL_CONTROLS = False
	#displayInfo("Dynamic joint chain successfully setup!\n")
		
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
			
		#if progressWindow(query=1, progress=1) >= 100:
			#break
			
		amount=((100 / i) * j)
		progressWindow(edit=1,progress=amount)
		progressWindow(edit=1,status=("Baking chain " + str(j) + " of " + str(i) + " :"))
		j+=1
		chainCtrl = str(obj)
		bakingJoints = "{"
		all_dyn_joints = getAttr(chainCtrl + ".allDynJoints")
		all_dyn_joints = all_dyn_joints.split(',')
		for joint in all_dyn_joints:
			bakingJoints = (bakingJoints + "\"" + joint + "\", ")	
		bakingJoints = bakingJoints.rstrip(', ')
		bakingJoints=(bakingJoints + "}")
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
		setAttr((chainCtrl + ".bakingState"), 1)
		#Print feedback to user
		print "All joints controlled by " + chainCtrl + " have now been baked!\n"
		
	progressWindow(endProgress = True)

#///////////////////////////////////////////////////////////////////////////////////////
#								DELETE DYNAMICS PROCEDURE
#///////////////////////////////////////////////////////////////////////////////////////
def delete_dynamic_chain():
	initialSel=mc.ls(selection=True)
	#Declare necessary variables
	chainCtrls=initialSel
	error=0
	for chainCtrl in chainCtrls:
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
			try:
				delete(getAttr(chainCtrl + ".nameOfFollicleSystem"))
			except Exception:
				pass

			
			# Delete the IK Handle attached
			baseJoint=str(getAttr(chainCtrl + ".baseJoint"))
			#delete(baseJoint + "ikHandle")
			
			# Delete the dynamic joints involved	
			#delete(baseJoint)
			
			# Delete blend joints and controls	
			#blend_controls = str(getAttr(chainCtrl + ".blendControl"))
			#delete(blend_controls)
			
			#Delete control object
			select(chainCtrl)
			group = pickWalk(d='up')
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

def delete_baked_frames():
	""" Remove all baked frames form a controllers dynamic chains"""
	chain_ctrls = ls(selection=True)
	for chain_ctrl in chain_ctrls:
		dyn_joints = getAttr('{0}.allDynJoints'.format(chain_ctrl))
		for joint in dyn_joints.split(','):
			cutKey(joint, clear = True)
			
def create_character_from_prefs():
	# XXX Doesn't do any error checking for names in xml file
	# XXX Only does joints.  What about attrs?
	global USING_ALL_CONTROLS
	item = fileDialog()
	try:
		prefs = xml_utils.ElementTree.parse(str(item))
	except SyntaxError as se:
		mel.warning("Unable to parse character prefs. Error: \n{0}".format(str(se)))
		return
	root = prefs.getroot()
	creation_dict = {}
	# Get all the presets and store them in a dictionary that can be retrieved later
	for child in root:
		if child.tag == 'presets':
			for preset in child.getchildren():
				creation_dict[preset.attrib['name']] = preset.attrib['allCtrls']
				
	for child in root:
		if child.tag == 'joints':
			for joint in child.getchildren():
				if creation_dict.has_key(joint.attrib['name']):
					USING_ALL_CONTROLS = creation_dict[joint.attrib['name']]
				if USING_ALL_CONTROLS:
					select(joint.attrib['controls'].split(','), replace=True)
					create_dynamic_chain()
				else:
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
	item = fileDialog2()
	all_ctrls = ls(selection=True)
	root = xml_utils.ElementTree.Element('data')
	joints = xml_utils.ElementTree.SubElement(root, 'joints')
	attrs = xml_utils.ElementTree.SubElement(root, 'attrs')
	presets = xml_utils.ElementTree.SubElement(root, 'presets')
	# Save the joints
	for ctrl in all_ctrls:
		uses_all_ctrls = getAttr('{0}.usesAllControls'.format(ctrl))
		if uses_all_ctrls:
			preset_info = xml_utils.ElementTree.SubElement(presets, 'preset')
			preset_info.set('allCtrls', 'True')
			preset_info.set('name', ctrl)
			controls = getAttr('{0}.allControls'.format(ctrl))
			joint_info = xml_utils.ElementTree.SubElement(joints, 'joint')
			joint_info.set('controls', controls)
			joint_info.set('name', ctrl)
		else:
			base_joint = getAttr('{0}.baseControl'.format(ctrl))
			end_joint = getAttr('{0}.endControl'.format(ctrl))
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
			'blend' : getAttr('{0}.blend'.format(ctrl)),
		        #'iterations' : getAttr('{0}.iterations'.format(ctrl))
		}
		attr_info.set('name', ctrl)
		for attr_name, attr_val in attr_dict.iteritems():
			attr_info.set(attr_name, str(attr_val))
	xml_utils.indent(root)
	tree = xml_utils.ElementTree.ElementTree(root)
	tree.write(str(item[0]))
	warning('{0} has been written.'.format(str(item[0])))

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
	frameLayout('creationOptions',h=175,
		borderStyle='etchedOut',
		collapsable=True,
		w=350,
		label="Dynamic Chain Creation Options:")
	frameLayout('creationOptions',e=1,cl=True)
	columnLayout(cw=350)
	#Stiffness
	floatSliderGrp('sliderStiffness',min=0,max=1,
		cw3=(60, 60, 60),
		precision=3,
		value=0.6,
		label="Stiffness:",
		field=True,
		cal=[(1, 'left'), (2, 'left'), (3, 'left')])
	#Damping
	floatSliderGrp('sliderDamping',min=0,max=100,
		cw3=(60, 60, 60),
		precision=3,
		value=10,
		label="Damping:",
		field=True,
		cal=[(1, 'left'), (2, 'left'), (3, 'left')])
	#Drag
	floatSliderGrp('sliderDrag',min=0,max=1,
		cw3=(60, 60, 60),
		precision=3,
		value=.5,
		label="Drag:",
		field=True,
		cal=[(1, 'left'), (2, 'left'), (3, 'left')])
	#Tip Constraint Checkbox
	separator(h=20,w=330)
	checkBoxGrp('tipConstraintCheckbox',cw=(1, 200),label="Create Tip Constraint : ")
	checkBoxGrp('stretchCheckbox',cw=(1, 200),label="Allow Joint Chain to Stretch: ")
	checkBoxGrp('linkToJoints', cw = (1, 200), label = "Link to Joints *Cannot be locked*: ")
	#separator -h 20  -w 330;
	setParent('..')
	setParent('..')
	#Button Layouts
	text("Note: If controls are in a non-hierarchy, select all controls: ")
	rowColumnLayout(nc=2,cw=[(1, 175), (2, 150)])
	text("Select base joint, shift select tip: \n")
	button(c=lambda *args: overlap_tool.create_dynamic_chain(),label="Make Dynamic")
	text("Select all ctrls and colliders: ")
	button(c=lambda *args: overlap_tool.collide_with_chain(),label="Make Collide")
	text("Select control: ")
	button(c=lambda *args: overlap_tool.delete_dynamic_chain(),label="Delete Dynamics")
	#text("Select control: ")
	#button(c=lambda *args: overlap_tool.delete_baked_frames(), label = "Delete Baked Frames")
	#text("Disable Dynamics: ")
	#button(c=lambda *args: overlap_tool.disable_dynamics(), label="Disable Dynamics")
	#text("Enable Dynamics: ")
	#button(c=lambda *args: overlap_tool.enable_dynamics(), label="Enable Dynamics")
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

if __name__ == "__main__":
	main()