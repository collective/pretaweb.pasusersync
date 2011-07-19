from zope.interface import implements, provides
from zope.component import queryUtility
from plone.i18n.normalizer.interfaces import IURLNormalizer
from Products.CMFCore.utils import getToolByName


from zope.app.component.hooks import getSite
from Products.membrane.interfaces import IUserAdder

from AccessControl import ClassSecurityInfo, ModuleSecurityInfo
from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.SecurityManagement import getSecurityManager
from AccessControl.SecurityManagement import noSecurityManager
from AccessControl.Permissions import manage_users as ManageUsers
from AccessControl.User import nobody, UnrestrictedUser
from AccessControl.SpecialUsers import emergency_user, system

from Products.CMFPlone.utils import _createObjectByType
from Acquisition import Implicit

#PERSON_TYPE = 'FSDPerson'
#CONTAINER_TYPE = 'FSDFacultyStaffDirectory'

class FacultyDirectoryUserAdder(Implicit):
    provides(IUserAdder)

    
    """
    An utility providing a means of adding a user to FacultyDirectory
    """
    def addUser(self, login, password, *kw):
        """
        Adds a user with specified id and username.  Any keyword
        arguments are set as properties on the user, if possible.
        """
        
        username = login
        firstname = login
        lastname = ' '
        id = login.replace('\\','_')
        id = id.replace('/','_')

        #id = queryUtility(IURLNormalizer).normalize(id, 'en')
        # should really use the utility but can't make it work under 2.5
        from normalize import baseNormalize
        id = baseNormalize(id)        

        if not (username and firstname and lastname):
            # Not enough info
            return

        portal = getSite()
        fd = getToolByName(site, 'facultystaffdirectory_tool')
        membrane = getToolByName(site, 'membrane_tool')
        workflow = getToolByName(site, 'portal.portal_workflow')
        root = fd.getDirectoryRoot()
        types = fd.getAddableInterfaceSubscribers()
        usertype = types[0]


        #Fool the security manager so we membrane can add users
        suser = UnrestrictedUser('Membrane Special User','',('Manager',), [])
        newSecurityManager(None, suser)

        brains = membrane.searchResults(meta_type=usertype, exact_getUserName=username)
        if brains:
            ob = brains[0].getObject()
        else:
            brains = membrane.searchResults(meta_type=usertype,getId=id)
            if brains:
                ob = brains[0].getObject()
            else:
                # create BelronUser

                _createObjectByType(usertype, root, id)

                ob = getattr(portal.users, id)
                ob.setUserName(username)
                ob.setFirstName(firstname)
                ob.setSurname(lastname)
                ob.update(*kw)

                # !!! note that we ALWAYS set a new password here!
                ob.setPassword(password)

                #import pdb;pdb.set_trace()
                ob.reindexObject()

        rs = workflow.getInfoFor(ob, 'review_state')
        if rs != 'enabled':
            workflow.doActionFor(ob, 'enable')

        #luf = portal.acl_users.ad.acl_users # LDAPUserFolder instance
        #samAcName = id.replace('obrien_','')
        #ldapusers = luf.searchUsers(sAMAccountName=samAcName)
        #if not len(ldapusers) == 0:
        #    props = portal.restrictedTraverse("@@belronuserprops_view").syncProps(id, ldapusers[0])
        #    portal.plone_log('Synced the following attributes for '+id+':'+str(props))


  

#sm = getSiteManager(site)
#sm.registerUtility(BelronUserAdderUtility, IUserAdder, "BelronUserAdderUtility")
