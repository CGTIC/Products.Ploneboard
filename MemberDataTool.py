try:
    from Products.CMFCore.interfaces.portal_memberdata import MemberData as IMemberData
    memberdata_interface = 1
except:
    memberdata_interface = 0

from Globals import InitializeClass, DTMLFile
from AccessControl import getSecurityManager, ClassSecurityInfo, Unauthorized
from Acquisition import aq_base, aq_parent
from BTrees.OOBTree import OOBTree
from OFS.SimpleItem import SimpleItem
from OFS.PropertyManager import PropertyManager
from OFS.ObjectManager import ObjectManager
from Products.BTreeFolder2.BTreeFolder2 import BTreeFolder2Base
from Products.CMFCore import CMFCorePermissions
from Products.CMFCore.ActionProviderBase import ActionProviderBase
from Products.CMFCore.utils import UniqueObject, getToolByName
from Products.CMFCore.PortalFolder import PortalFolder
from Products.Archetypes.debug import log
from Products.Archetypes import registerType
from Products.CMFMember import PKG_NAME
from Products.CMFMember.Extensions.Workflow import triggerAutomaticTransitions
from Products.CMFMember.types.Member import Member

from Products.Archetypes.public import *

import pdb

from Products.CMFCore.MemberDataTool import MemberDataTool as DefaultMemberDataTool
_marker = []

class TempFolder(PortalFolder):
    portal_type = meta_type = 'MemberArea'
    

class MemberDataTool(BTreeFolder2Base, PortalFolder, DefaultMemberDataTool):
    if memberdata_interface:
        __implements__ = (IMemberData, ActionProviderBase.__implements__)

    security=ClassSecurityInfo()

    manage_options=(
        {'label':'Schema','action':'schemaForm'},
        ) #+DefaultMemberDataTool.manage_options

    id = 'portal_memberdata'
    portal_type = meta_type = PKG_NAME + ' Tool'

    _actions = []

    _defaultMember = None

    memberdata_actions = (
        { 'id': 'view',
          'name': 'View',
          'action': 'folder_contents',
          'permissions': (CMFCorePermissions.View,),
          'category'      : 'folder'
        },
        { 'id'            : 'edit',
          'name'          : 'Edit',
          'action'        : 'folder_edit_form',
          'permissions'   : (CMFCorePermissions.ManageProperties,),
          'category'      : 'folder'
        },
        { 'id'            : 'localroles',
          'name'          : 'Local Roles',
          'action'        : 'folder_localrole_form',
          'permissions'   : (CMFCorePermissions.ManageProperties,),
          'category'      : 'folder'
        })


    manage_options=( BTreeFolder2Base.manage_options +
                     ActionProviderBase.manage_options
                   )  +({'label':'Schema','action':'schemaForm'}, ) 
    schemaForm = DTMLFile('dtml/schemaForm',globals())


    ##IMPL DETAILS
    def __init__(self):
        BTreeFolder2Base.__init__(self, self.id)
        self.typeName = 'Member'  # The name used for the factory in types_tool
        self.setTitle('Member profiles')


    security.declarePublic('__call__')
    def __call__(self):
        """Invokes the default view."""
        view = _getViewFor(self, 'view', 'folderlisting')
        if getattr(aq_base(view), 'isDocTemp', 0):
            return apply(view, (self, self.REQUEST))
        else:
             return view()


    security.declareProtected( CMFCorePermissions.View, 'view' )    
    def view(self, **kwargs):
        """Invokes the default view."""
        view = _getViewFor(self, 'view', 'folderlisting')
        if getattr(aq_base(view), 'isDocTemp', 0):
            return apply(view, (self, self.REQUEST))
        else:
             return view()


    security.declarePublic('index_html')
    def index_html(self, REQUEST, RESPONSE):
        """Member search form"""
        search_form = self.restrictedTraverse('member_search_form')
        return search_form(REQUEST, RESPONSE)


    security.declarePrivate('_deleteMember')
    def _deleteMember(self, id):
        """Remove a member"""
        self._delObject(id)

    
    ##PORTAL_MEMBERDATA INTERFACE IMPL
    security.declarePrivate('listActions')
    def listActions(self, info=None):
        """
        Return actions provided via tool.
        """
        return self._actions

    # XXX fixme
    security.declarePrivate('getMemberDataContents')
    def getMemberDataContents(self):
        '''
        Returns a list containing a dictionary with information 
        about the _members BTree contents: member_count is the 
        total number of member instances stored in the memberdata-
        tool while orphan_count is the number of member instances 
        that for one reason or another are no longer in the 
        underlying acl_users user folder.
        The result is designed to be iterated over in a dtml-in
        '''

        member_ids = [m.getUserName() for m in self.objectValues()]
        membership_tool= getToolByName(self, 'portal_membership')
        user_ids = membership_tool.listMemberIds()
        oc = 0
        for id in member_ids:
            if id not in user_ids:
                oc += 1
                
        return [{
            'member_count' : len(member_ids),
            'orphan_count' : oc
            }]

    #XXX FIXME
    #This is a brain dead implementation as it does not use the catalog.  Fix!
    security.declarePrivate( 'searchMemberDataContents' )
    def searchMemberDataContents( self, search_param, search_term ):
        """ Search members """
        res = []

        if search_param == 'username':
            search_param = 'id'

        for user_wrapper in self.objectValues():
            searched = getattr( user_wrapper, search_param, None )
            if searched is not None and searched.find(search_term) != -1:
                res.append( { 'username' : getattr( user_wrapper, 'id' )
                            , 'email' : getattr( user_wrapper, 'email', '' )
                            }
                          )

        return res



    #XXX FIXME
    #This is a brain dead implementation lifted from Plone -- it does not use the catalog.  Fix!
    def searchForMembers( self, REQUEST=None, **kw ):
        """ """
        if REQUEST:
            dict = REQUEST
        else:
            dict = kw
        
        name = dict.get('name', None)
        email = dict.get('email', None)
        roles = dict.get('roles', None)
        last_login_time = dict.get('last_login_time', None)
        is_manager = self.checkPermission('Manage portal', self)
            
        if name:
            name = name.strip().lower()
        if not name:
            name = None
        if email:
            email = email.strip().lower()
        if not email:
            email = None


        md = self.portal_memberdata
        
        res = []
        portal = self.portal_url.getPortalObject()
        acl_users = portal.acl_users
        if hasattr(acl_users, 'getPureUsers'):
            # for GRUF
            getUsers = acl_users.getPureUsers
        else:
            getUsers = acl_users.getUsers
            
        for u in getUsers():
            user = md.wrapUser(u)
            if not (user.listed or is_manager):
                continue
            # XXX fix me!  remove these try blocks and use accessor method
            if name:
                userfullname = None
                try:
                    userfullname = user.getFullname()
                except AttributeError:
                    try:
                        userfullname = user.fullname
                    except AttributeError:
                        pass
                
                if (u.getUserName().lower().find(name) == -1) and \
                  ((not userfullname) or userfullname.lower().find(name) == -1):
                    continue
            if email:
                useremail = None
                try:
                    useremail = user.getEmail()
                except AttributeError:
                    try:
                        useremail = user.email
                    except AttributeError:
                        pass

                if (not useremail) or useremail.lower().find(email) == -1:
                    continue
            if roles:
                user_roles = user.getRoles()
                found = 0
                for r in roles:
                    if r in user_roles:
                        found = 1
                        break
                if not found:
                    continue
            if last_login_time:
                if user.last_login_time < last_login_time:
                    continue
            res.append(user)

        return res


    # XXX fixme
    security.declarePrivate('pruneMemberDataContents')
    def pruneMemberDataContents(self):
        '''
        Compare the user IDs stored in the member data
        tool with the list in the actual underlying acl_users
        and delete anything not in acl_users

        The impl can override the pruneOrphan(id) method to do things
        like manage its workflow state. The default impl will remove.
        '''
        
        member_ids = [m.getUserName() for m in self.objectValues()]
        membership_tool= getToolByName(self, 'portal_membership')
        user_ids = membership_tool.listMemberIds()

        for id in members_ids:
            if id not in user_ids:
                self.pruneOrphan(id)


    security.declarePrivate('wrapUser')
    def wrapUser(self, user):
        '''
        If possible, returns the Member object that corresponds
        to the given User object.
        '''
        try:
            #import pdb; pdb.set_trace()
            name = user.getUserName()
            m = self.get(name, None)
            if not m:
                ## XXX Delegate to the factory and create a new site specific
                ## member object for this user
                addMember=getMemberFactory(self, self.typeName)
                addMember(name)
                m = self.get(name)
                m.setUser(user)
                # trigger any workflow transitions that need to occur
                triggerAutomaticTransitions(m) 

            # Return a wrapper with self as containment and
            # the user as context following CMFCore portal_memberdata
            return m.__of__(self).__of__(user)
        except:
            import traceback
            import sys
            sys.stdout.write('\n'.join(traceback.format_exception(*sys.exc_info())))
            #import pdb; pdb.set_trace()
            raise


    security.declarePrivate('registerMemberData')
    def registerMemberData(self, m, id):
        '''
        Adds the given member data to the _members dict.
        This is done as late as possible to avoid side effect
        transactions and to reduce the necessary number of
        entries.
        '''
        self._setObject(id, m)

    def _getMemberInstance(self):
        """Get an instance of the Member class.  Used for 
           extracting default property values, etc."""
        if self._defaultMember is None:
            tempFolder = PortalFolder('temp').__of__(self)
            getMemberFactory(tempFolder, self.typeName)('default')
            self._defaultMember = getattr(tempFolder,'default')
            getattr(tempFolder,'default').unindexObject()
            # don't store _defaultMember in the catalog
            tempFolder.unindexObject() 
            # don't store _defaultMember in the catalog
            self._defaultMember.unindexObject() 
        return self._defaultMember


    security.declarePublic('getProperty')
    def getProperty(self, id, default=None):
        """Get the property 'id', returning the optional second
           argument or None if no such property is found."""

        # First try to get the default value from MemberDataTool properties
        # so that one can set default values TTW
        _marker = {}
        p = DefaultMemberDataTool.getProperty(self, id, _marker)
        if p != _marker:
            return p

        # Fall back to the default value from the Member schema
        # Create a temporary member if needed.
        m = self._getMemberInstance()

        try:
            return m._getProperty(id)
        except:
            return None
       

    ## Folderish Methods
    def allowedContentTypes(self):
        ## XXX we want anything that is a subclass of Member?
        ## XXX or define a real registration mechinism, same for
        ## XXX all_meta_types
        tt = getToolByName(self, 'portal_types')
        ti = tt.getTypeInfo(self.typeName)
        return [ti]

    def filtered_meta_types(self, user=None):
        # Filters the list of available meta types.
        allowedTypes = [self._getMemberInstance()._getTypeName()]
        meta_types = []
        for meta_type in self.all_meta_types():
            if meta_type['name'] in allowedTypes:
                meta_types.append(meta_type)
        return meta_types


    security.declareProtected(CMFCorePermissions.ListPortalMembers, 'contentValues')
    def contentValues(self, spec=None, filter=None):
        objects = [v.__of__(self) for v in self.objectValues()]
        l = []
        for v in objects:
            id = v.getId()
            try:
                if getSecurityManager().validate(self, self, id, v):
                    l.append(v)
            except Unauthorized:
                pass
        return l

    def _getUserFromUserFolder(self, name):
        return self.acl_users.getUser(name).__of__(self.acl_users)
       
    def _checkId(self, id, allow_dup=0):
        PortalFolder._checkId(self, id, allow_dup)
        BTreeFolder2Base._checkId(self, id, allow_dup)


    # register type type of Member object that the MemberDataTool will store
    def registerType(self, new_type_name):
        self.typeName = new_type_name
        self._defaultMember = None # nuke the default member (which was of the old Member type)
        typestool=getToolByName(self, 'portal_types')
        typestool.MemberArea.allowed_content_types=(new_type_name,)


    # Migrate members when changing member type
    # 1) rename old member to some temp name
    # 2) create new member with old id
    # 3) transfer user assets to new member
    # 4) delete old member
    #
    # new_type_name = meta_type for the new Member type
    # workflow_transfer = dict mapping each state in old members to a list of transitions
    #       that must be executed to move the new member to the old member's state
    def migrateMembers(self, out, new_type_name, workflow_transfer={}):
        
        self.registerType(new_type_name)
        factory = getMemberFactory(self, self.typeName)

        portal = getToolByName(self, 'portal_url').getPortalObject()
        workflow_tool = getToolByName(self, 'portal_workflow')

        for m in self.objectIds():
            old_member = self.get(m)
            temp_id = 'temp_' + m
            while self.get(temp_id):
                temp_id = '_' + temp_id
            old_member._migrating = 1
            self.manage_renameObjects([m], [temp_id])
            factory(m)
            old_member = self.get(temp_id)
            new_member = self.get(m)
            # copy over old member attributes
            new_member._migrate(old_member, [], out)

            # copy workflow state
            old_member_state = workflow_tool.getInfoFor(old_member, 'review_state', '')
            print >> out, 'state = %s' % (old_member_state,)
            transitions = workflow_transfer.get(old_member_state, [])
            print >> out, 'transitions = %s' % (str(transitions),)
            for t in transitions:
                workflow_tool.doActionFor(new_member, t)

            self.manage_delObjects(temp_id)
        from Products.CMFMember.Extensions.Install import setupNavigation
        setupNavigation(self, out, new_type_name)


    ##SUBCLASS HOOKS
    security.declarePrivate('pruneOrphan')
    def pruneOrphan(self, id):
        """Called when a member object exists for something not in the
        acl_users folder
        """
        self._deleteMember(id)

    def setMemberSchema(self,member_schema,REQUEST=None):
        ''' '''
        member_schema=member_schema.strip().replace('\r','')
        schema=eval(member_schema)
        self.memberSchema=Member.schema + schema
        self.member_schema=member_schema
        
        if REQUEST:
            REQUEST.RESPONSE.redirect(REQUEST['HTTP_REFERER'])
            
    def getMemberSchema(self):
        ''' '''
        return getattr(self,'memberSchema',Member.schema ) #+ Schema((StringField('sssssss')))

# Put this outside the MemberData tool so that it can be used for
# conversion of old MemberData during installation
def getMemberFactory(self, type_name):
    """return a callable that is the registered object returning a
    contentish member object"""
    # Assumptions: there is a types_tool type called Member, you
    # want one of these in the folder, changing this changes the
    # types of members in your site.
    types_tool = getToolByName(self, 'portal_types')
    ti = types_tool.getTypeInfo(type_name)

    try:
        p = self.manage_addProduct[ti.product]
        action = getattr(p, ti.factory, None)
    except AttributeError:
        raise ValueError, 'No type information installed'
    if action is None: 
        raise ValueError, ('Invalid Factory for %s'
                           % ti.getId())
    return action


from Products.CMFCore.utils import _verifyActionPermissions

# XXX update this for 1.1
def _getViewFor(obj, view='view', default=None):
    ti = obj.getTypeInfo()
    if ti is not None:
        actions = ti.getActions()
        for action in actions:
            if action.get('id', None) == default:
                if default and type(default) != type(''):
                    default = default['action']
                return obj.restrictedTraverse(default)

        # "view" action is not present or not allowed.
        # Find something that's allowed.
        #for action in actions:
        #    if _verifyActionPermissions(obj, action)  and action.get('action','')!='':
        #        return obj.restrictedTraverse(action['action'])
        raise 'Unauthorized', ('No accessible views available for %s' %
                               '/'.join(obj.getPhysicalPath()))
    else:
        raise 'Not Found', ('Cannot find default view for "%s"' %
                            '/'.join(obj.getPhysicalPath()))


InitializeClass(MemberDataTool)
