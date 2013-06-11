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
DYN_CONTROLLER_SIZE = 5
MAGNETISM = 1

DYN_SUFFIX = '_DYN'
BLND_SUFFIX = '_BLND'

ITERATIONS = 10

DYN_SMOOTHNESS = 1.0
USING_ALL_CONTROLS = False
HAS_TIP_CONSTRAINT = False
ALLOW_CHAIN_STRETCH = False

NODE_SUFFIX = 'CON'
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
	#add_name_to_attr(jointCtrlObj, {'blendControl' : new_control})
	#parent(new_control, world=True)
	
	# Turn off visibility on new controls
	#addAttr(jointCtrlObj, ln="blendCtrlVis", at='bool', keyable=True)
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
	global DYN_SMOOTHNESS
	DYN_SMOOTHNESS = float(floatSliderGrp('sliderSmoothness', query = 1, value = 1))
	addAttr(jointCtrlObj,
                min=0,ln="controllerSize",max=500,keyable=True,at='double',dv=DYN_CONTROLLER_SIZE)
	addAttr(jointCtrlObj,
	        min=0, ln="attraction", max=1, keyable=True, at='double', dv=MAGNETISM)
	addAttr(jointCtrlObj,
	        min=0, ln='smoothness', max=10, keyable=True, at='double', dv=DYN_SMOOTHNESS)
	addAttr(jointCtrlObj,
	        min=0, ln='conserve', max=1, keyable=True, at='double', dv=1.0)

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
		
	if len(joint_names) < len(joint_list):
		constrainer.append(joint_names[-1])
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
	#for i, cur_joint in enumerate(blend_joints):
		#try:
			#scaleConstraint(cur_joint, constrainer[i])
		#except RuntimeError as e:
			#displayInfo("Unable to perform scale constrain on {0}".format(constrainer[i]))
		#try:
			#parentConstraint(cur_joint, constrainer[i], mo=True)
		#except RuntimeError as e:
			#displayInfo("Blended joints could not constrain to original joints.\n")
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
			#if isinstance(child, Transform) and 'CON' in str(child):
			if str(child).endswith(NODE_SUFFIX):
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
			# CHANGE BACK TO CON FOR CONTROLLERS
			if to_next_control and str(child).endswith(NODE_SUFFIX):
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

def get_first_joint(node):
	""" Find the first joint by recursively going through the hierarchy.
	Args:
		node : (str)
	        	Node which to start searching.
	                
	"""
	children = node.getChildren()
	if not children:
		return None
	else:
		for child in children:
			if isinstance(child, Joint):
				return child
			else:
				first_joint = get_first_joint(child)
	return first_joint

def add_goal_attrs(jointCtrlObj, particle_system, goalPPs):
	""" Get all particle goals and add them as attributes to the dynamic controller.
	Args:
		jointCtrlObj : (str)
			Dynamic joint controller
		particle_system : (str)
			Particle system attached to the curve
		goalPPs : (list)
			List of all goalPP values retrieved.
			
	"""
	goal_attrs = []
	# Enumerate through the values and create an expression and attach to the joint controller
	for i, goalPP in enumerate(goalPPs):			
		addAttr(jointCtrlObj,
			min=0,ln='goal{0}'.format(str(i)),max=1,keyable=True,at='float',dv=goalPP)

		goal_attrs.append(expression(
		        s = 'particle -e -or {i} -at goalPP -fv `getAttr {val}` {particle} ;'.format(
		                i = str(i),
		                particle = particle_system,
		                val = '{0}.goal{1}'.format(jointCtrlObj, str(i)),
		        ), 
		        n='goal{0}'.format(i)))
	return goal_attrs
		
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
			baseJoint = get_first_joint(base_ctrl) 
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
			baseJoint = get_first_joint(base_ctrl)
			#base_children = base_ctrl.getChildren()
			#baseJoint = [node for node in base_children if isinstance(node, Joint)][0]
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
	curve = build_curve_from_joint(jointPos)
	#Make curve dynamic.
	select(joint_list[0], joint_list[-1], curve)
	ik_info = ikHandle(ccv=False,sol='ikSplineSolver',simplifyCurve=True)
	ik_handle = ik_info[0]
	# Hide the ik handles visibility
	change_visibility([ik_handle], 0)
	select(curve)
	soft_curve = ls(selection=True)[0]
	mm.eval('dynCreateSoft 0 0 1 1 0')
	goal_curve = "copyOf{0}".format(str(curve))
	particle_system = [item for item in soft_curve.getChildren() if str(item).endswith('Particle')][0]
	goalPPs = getAttr('{0}.goalPP'.format(particle_system))
	#Create Joint Chain Controller Object
	jointCtrlObjArray=[]
	jointCtrlObjArray.append(str(createNode('implicitSphere')))
	jointCtrlObjArray=pickWalk(d='up')
	jointCtrlObj=jointCtrlObjArray[0]
	# Add dynamic attribute
	add_dynamic_attributes(jointCtrlObj)
	#Point Constrain Control Object to the end joint
	pointConstraint(endJoint,jointCtrlObj)

	#Rename Ctrl Obj
	jointCtrlObj=str(rename(jointCtrlObj, (baseJoint + "DynChainControl")))

	constraint_weights = constrain_joints(
	        controls, 
	        joint_list, 
	        blend_joints, 
	        joints_per_control
	)
	dupe_nodes = add_duplicate_blend_controls(jointCtrlObj, controls, blend_joints)
	dupe_controls = []
	for node in dupe_nodes:
		if len(dupe_controls) < len(controls) and str(node).endswith('{0}'.format(NODE_SUFFIX)):
			dupe_control = str(rename(node, 'OVR_{0}'.format(node)))
			dupe_controls.append(dupe_control)
	
	# Build Clusters from curve
	clusters = build_clusters_from_curve(goal_curve, len(jointPos))
	
	# Constrain the clusters to the duplicate controls
	for i, dupe_control in enumerate(dupe_controls):
		scaleConstraint(dupe_control, clusters[i])
		parentConstraint(dupe_control, clusters[i])
		# copy the keys over from control
		item = copyKey(controls[i])
		if item != 0:
			pasteKey(dupe_control)
	
	# Add spring object
	#spring_system = spring(particle_system)
	
	# Connect attributes on the controller sphere to the follicle node
	particle_to_ctrl_attrs = {
	        'attraction' : 'goalWeight[0]',
	        'smoothness' : 'goalSmoothness',
	        'conserve' : 'conserve',
        }
	connect_controller_to_system(jointCtrlObj, particle_system, particle_to_ctrl_attrs)
	#Connect scale of controller to the size attr
	connectAttr((jointCtrlObj + ".controllerSize"),
                    (jointCtrlObj + ".scaleX"), f=True)
	connectAttr((jointCtrlObj + ".controllerSize"), 
                    (jointCtrlObj + ".scaleY"), f=True)
	connectAttr((jointCtrlObj + ".controllerSize"), 
                    (jointCtrlObj + ".scaleZ"), f=True)
	
	#Lock And Hide Attributes on Control Object.
	lock_and_hide_attr(jointCtrlObj)
	
	# Create all the expressions for each goal
	particle_shape = particle_system.getChildren()[0]
	goal_expressions = add_goal_attrs(jointCtrlObj, particle_shape, goalPPs)	
		
	# Create a new group
	dynamic_group = group(name='{0}_DynamicChainGroup'.format(baseJoint))
	# Parent all the controls to new group
	parent(joint_list[0], dynamic_group)
	parent(jointCtrlObj, dynamic_group)
	parent(ik_handle, dynamic_group)
	#parent(spring_system[0], dynamic_group)
	parent(clusters, dynamic_group)
	parent(soft_curve, dynamic_group)
	parent(goal_curve, dynamic_group)
	parent(dynamic_group, controls[0].getParent())
	# Store all the names to the controls as an attr.
	obj_names = {
	        'nameOfGoalCurve' : goal_curve,
	        'baseJoint' : baseJoint,
	        'endJoint' : endJoint,
	        'linkedBaseJoint' : joint_names[0],
	        'linkedEndJoint' : joint_names[-1],
	        'baseControl' : controls[0],
	        'endControl' : controls[-1],
	        'allControls' : ','.join([str(control) for control in controls]),
	        'allDynJoints' : ','.join([str(joint) for joint in joint_list]),
	        'goalExpressions' : ','.join([str(exp) for exp in goal_expressions]),
	        'duplicateControls' : ','.join([str(control) for control in dupe_controls]),
	}
	add_name_to_attr(jointCtrlObj, obj_names)
	
	# Print feedback for user
	select(jointCtrlObj)
	
	displayInfo("Dynamic joint chain successfully setup!\n")
		

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
		if not mel.attributeExists("allDynJoints", chainCtrl):
			error=1
			mel.warning("Please select a chain controller. No dynamics were deleted.")
		
		if error == 0:
			# Apply keys to original controls
			controls = getAttr('{0}.allControls'.format(chainCtrl)).split(',')
			controls = [str(item) for item in controls]
			dup_controls = getAttr('{0}.duplicateControls'.format(chainCtrl)).split(',')
			dup_controls = [str(item) for item in dup_controls]
			for control in dup_controls:
				try:
					delete(control)
				except Exception:
					pass
			# Copy all the keys from the duplicated control to original.
			# Cut all the keys from the original control since they should have
			# been copied to the duplicated
			for i, control in enumerate(dup_controls):
				keys = copyKey(control)
				if keys != 0:
					cutKey(controls[i], clear=True)
					pasteKey(controls[i])
			# Remove all the goal expressions
			goal_expressions = getAttr('{0}.goalExpressions'.format(chainCtrl)).split(',')
			goal_expressions = [str(item) for item in goal_expressions]
			select(goal_expressions)
			delete(goal_expressions)
			select(chainCtrl)
			dynamic_group = pickWalk(d = 'up')
			delete(dynamic_group)
		#Print feedback to the user.
		print "Dynamics have been deleted from the chain.\n"
			
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
		#uses_all_ctrls = getAttr('{0}.usesAllControls'.format(ctrl))
		#if uses_all_ctrls:
			#preset_info = xml_utils.ElementTree.SubElement(presets, 'preset')
			#preset_info.set('allCtrls', 'True')
			#preset_info.set('name', ctrl)
			#controls = getAttr('{0}.allControls'.format(ctrl))
			#joint_info = xml_utils.ElementTree.SubElement(joints, 'joint')
			#joint_info.set('controls', controls)
			#joint_info.set('name', ctrl)
		#else:
		base_joint = getAttr('{0}.baseControl'.format(ctrl))
		end_joint = getAttr('{0}.endControl'.format(ctrl))
		joint_info = xml_utils.ElementTree.SubElement(joints, 'joint')
		joint_info.set('base', base_joint)
		joint_info.set('end', end_joint)
		joint_info.set('name', ctrl)
	
		# Save the attrs
		attr_info = xml_utils.ElementTree.SubElement(attrs, 'attr')
		attr_dict = {
			'smoothness' : getAttr('{0}.smoothness'.format(ctrl)),
			'conserve' : getAttr('{0}.conserve'.format(ctrl)),
			'attraction' : getAttr('{0}.attraction'.format(ctrl)),
			'controllerSize' : getAttr('{0}.controllerSize'.format(ctrl)),
		}
		attrs = listAttr(ctrl)
		# Add all the goals
		for attr in attrs:
			if str(attr).startswith('goal') and str(attr) != 'goalExpressions':
				attr_dict[str(attr)] = getAttr('{0}.{1}'.format(ctrl, attr))
		attr_info.set('name', ctrl)
		for attr_name, attr_val in attr_dict.iteritems():
			attr_info.set(attr_name, str(attr_val))
	xml_utils.indent(root)
	tree = xml_utils.ElementTree.ElementTree(root)
	tree.write(str(item[0]))
	warning('{0} has been written.'.format(str(item[0])))


#///////////////////////////////////////////////////////////////////////////////////////
# UI
#///////////////////////////////////////////////////////////////////////////////////////

#///////////////////////////////////////////////////////////////////////////////////////
#								MAIN WINDOW
#///////////////////////////////////////////////////////////////////////////////////////
def main():
	test = OverlapWindow()
	test.create()
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
		collapsable=False,
		w=350,
		label="Dynamic Chain Creation Options:")
	frameLayout('creationOptions',e=1,cl=True)
	columnLayout(cw=350)
	#Stiffness
	floatSliderGrp('sliderSmoothness',min=0,max=10,
		cw3=(60, 60, 60),
		precision=3,
		value=3,
		label="Smoothness:",
		field=True,
		cal=[(1, 'left'), (2, 'left'), (3, 'left')])
	##Damping
	#floatSliderGrp('sliderDamping',min=0,max=100,
		#cw3=(60, 60, 60),
		#precision=3,
		#value=10,
		#label="Damping:",
		#field=True,
		#cal=[(1, 'left'), (2, 'left'), (3, 'left')])
	##Drag
	#floatSliderGrp('sliderDrag',min=0,max=1,
		#cw3=(60, 60, 60),
		#precision=3,
		#value=.5,
		#label="Drag:",
		#field=True,
		#cal=[(1, 'left'), (2, 'left'), (3, 'left')])
	#Tip Constraint Checkbox
	separator(h=20,w=330)
	#checkBoxGrp('tipConstraintCheckbox',cw=(1, 200),label="Create Tip Constraint : ")
	#checkBoxGrp('stretchCheckbox',cw=(1, 200),label="Allow Joint Chain to Stretch: ")
	#checkBoxGrp('linkToJoints', cw = (1, 200), label = "Link to Joints *Cannot be locked*: ")
	#separator -h 20  -w 330;
	setParent('..')
	setParent('..')
	#Button Layouts
	text("Note: If controls are in a non-hierarchy, select all controls: ")
	rowColumnLayout(nc=2,cw=[(1, 175), (2, 150)])
	text("Select base joint, shift select tip: \n")
	button(c=lambda *args: overlap_tool.create_dynamic_chain(),label="Make Dynamic")
	#text("Select all ctrls and colliders: ")
	#button(c=lambda *args: overlap_tool.collide_with_chain(),label="Make Collide")
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
	#separator(h=20,w=330)
	#text("                               -Bake Joint Animation-")
	#rowColumnLayout('bakeRowColumn',nc=3,cw=[(1, 100), (2, 100)])
	#text("Start Frame: ")
	#text("End Frame:")
	#text("Select Control:")
	#intField('startFrame')
	#intField('endFrame',value=400)
	#button(c=lambda *args: overlap_tool.bake_dynamic_chain(),label="Bake Dynamics")
	
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