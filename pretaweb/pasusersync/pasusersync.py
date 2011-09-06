
import logging

from Products.CMFCore.utils import getToolByName
from Products.Five import BrowserView
from Products.PluggableAuthService.interfaces.plugins import IUserAdderPlugin, IPropertiesPlugin, IUserFactoryPlugin
from Products.PlonePAS.sheet import MutablePropertySheet
from Products.Archetypes.config import REFERENCE_CATALOG

class PASUserSync(BrowserView):

    def __init__ (self, *args, **kwargs):
        BrowserView.__init__ (self, *args, **kwargs)
        self.portal = getToolByName(self.context, "portal_url")  .getPortalObject()


    def __call__ (self):

        request = self.request
        portal = getToolByName(self.context, "portal_url")  .getPortalObject()
        listPlugins = portal.acl_users.plugins.listPlugins


        # Get paramitors and corrispondign objects

        from_pluginid = request.get ("from")
        to_pluginid = request.get("to")

        # Allowing for more specific definition of the to property manager and
        # user manager
        if to_pluginid is None:
            to_properties_pluginid = request.get("to_properties")
            to_manager_pluginid = request.get("to_manager")
            to_userfactory_pluginid = request.get("to_userfactory")
        else:
            to_properties_pluginid = to_pluginid
            to_manager_pluginid = to_pluginid
            to_userfactory_pluginid = to_pluginid


        # Get plugin objects

        from_properties_plugin = None
        to_properties_plugin = None
        to_manager_plugin = None
        to_userfactory_plugin = None

        for pluginId, p in listPlugins(IPropertiesPlugin):
            if p.id == from_pluginid:
                from_properties_plugin = p
            elif pluginId == to_properties_pluginid:
                to_properties_plugin = p


        for pluginId, p in listPlugins(IUserAdderPlugin):
            if pluginId == to_manager_pluginid:
                to_manager_plugin = p
                break;
                
        for pluginId, p in listPlugins(IUserFactoryPlugin):
            if pluginId == to_userfactory_pluginid:
                to_userfactory_plugin = p
                break;
                


        # Check we have everything

        if not (to_manager_plugin and to_properties_plugin and to_userfactory_plugin and from_properties_plugin):
            raise Exception ("Cound not find needed plugin")


        # Do Sync

        return self.sync (from_properties_plugin, to_manager_plugin, to_properties_plugin, to_userfactory_plugin)



    #
    # Syncing
    #

    def sync (self, from_properties, to_manager, to_properties, to_userfactory):
    


        # Stats
        cadds = 0
        cremoves = 0
        cupdates = 0
        cnotupdates = 0

        doneUsers = set()
        for userInfo in self.portal.acl_users.searchUsers():

            # Do sync opertaions on a valid and not-done user
            uid = userInfo["id"]
            if uid not in doneUsers:
                doneUsers.add (uid)

                logging.info ("sync %s...", uid)


                user = self.getUser(uid)
                if user is None:
                    logging.info ("%s could not get user object.", uid)
                else:

                    # if None is returned from the followign, that would mean
                    # the plugin does not manage that user
                    fprop = self.getPropertiesForUser (from_properties, user)
                    tprop = self.getPropertiesForUser (to_properties, user)


                    # Operation on the user - update, add, remove, noop.
                    # Operation is determined by which pluging returns valid
                    # property sheets. 
                    if fprop and tprop:
                        if self.sync_update (user, fprop, tprop, to_userfactory):
                            logging.info ("%s: updated.", uid)
                            cupdates += 1
                        else:
                            logging.info ("%s: up to date.", uid)
                            cnotupdates += 1

                    elif fprop and (tprop is None):
                        self.sync_add (uid, to_manager, fprop, to_properties, to_userfactory)
                        logging.info ("%s: added.", uid)
                        cadds += 1

                    elif (fprop is None) and tprop:
                        self.sync_remove (uid, to_manager)
                        logging.info ("%s: removed.", uid)
                        cremoves += 1

                    else:
                        # noop - Do nothing
                        logging.info ("%s: sync not required.", uid)
                        cnotupdates += 1
                        


                    
        return "adds=%s updates=%s removes=%s not_updated=%s" % (cadds, cupdates, cremoves, cnotupdates)




    #
    # Sync Opertions
    #


    def sync_update (self, user, fprop, tprop, to_userfactory):

        updated_fields = []
        
        if isinstance (tprop, MutablePropertySheet):

            tpropMap = tprop.propertyMap()
            tkeys = set([p["id"] for p in tpropMap])

            # iterate from properties
            fpropMap = fprop.propertyMap()
            for propInfo in fpropMap:
                key = propInfo["id"]
                if key in tkeys:
                    fvalue = fprop.getProperty(key)
                    tvalue = tprop.getProperty(key)
                    
                                        
                    # compare value, is diff then update
                    # because there are different idears of Null. we don't want to override '' with None
                    if (fvalue or tvalue) and (fvalue != tvalue):
                        updated_fields.append(key)
                        tprop.setProperty (user, key, fvalue)    
                        
                        

        if len(updated_fields) > 0:

            if tprop.hasProperty("uid"):
                uid = tprop.getProperty("uid")
                referenceCatalog = getToolByName (self.portal, REFERENCE_CATALOG)
                usero = referenceCatalog.lookupObject (uid)
            else:
                ruser = to_userfactory.createUser (user.getId(), user.getName())
                if hasattr(ruser, "_getMembraneObject"):
                    usero = ruser._getMembraneObject()
                elif hasattr(user, "reindexObject"):
                    usero = ruser
                else:
                    usero = None
                
            if usero is not None:
                usero.reindexObject(updated_fields)
                
            return True

        else:
            return False
        
        
        
        

    def sync_add (self, uid, to_manager, fprop, to_properties, to_userfactory):
        password = getToolByName(self.portal, 'portal_registration').generatePassword ()

        # do the deed
        to_manager.doAddUser (uid, password)


        # roperties Update
        user = self.getUser(uid)
        tprop = self.getPropertiesForUser (to_properties, user)
        self.sync_update (user, fprop, tprop, to_userfactory)




    def sync_remove (self, uid, to_manager):
        to_manager.doDeleteUser (uid)




    #
    # Helper functions to retreive users and their properties
    #


    def getUser (self, uid):
        try:
            user = self.portal.acl_users.getUser(uid)
        except Exception, e:
            logging.error ("error in getting user '%s'", e)
            user = None
        return user
    

    def getPropertiesForUser (self, plugin, user):
        try:
            prop = plugin.getPropertiesForUser(user)
        except:
            prop = None


        if not(prop and len(prop.propertyMap())): 
            prop = None
            

        return prop
            




